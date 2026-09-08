"""The data plane, end to end on a temporary warehouse: bronze keeps what it got,
silver keeps no personal data, gold reconciles and names only registered systems, and
a reader loads gold from the pointer with no catalog. Runs in the data-plane
environment (src/requirements-data.txt); the main environment skips it.

Serves: BR-2, BR-7. Tests: T1-MD-02 (personal data cannot reach a prompt because it
never reaches gold).
"""

from __future__ import annotations

import pathlib

import pytest

pytest.importorskip("dagster")
pytest.importorskip("pyiceberg")
pytest.importorskip("presidio_analyzer")

FIXTURE = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "evidence.csv"
PLANTED = ["Jane Doe", "jane.doe@windrow-corp.com", "10.20.30.40", "Marcus Vane", "+1 415 555 0142"]


@pytest.fixture(scope="module")
def warehouse(tmp_path_factory, monkeypatch_module):
    d = tmp_path_factory.mktemp("lakehouse")
    monkeypatch_module.setenv("LAKEHOUSE_WAREHOUSE", (d / "warehouse").as_uri())
    monkeypatch_module.setenv("LAKEHOUSE_CATALOG", f"sqlite:///{(d / 'catalog.db').as_posix()}")
    monkeypatch_module.setenv("EVIDENCE_SOURCE_CSV", str(FIXTURE))
    from provenance.data.run import run

    ok, checks = run()
    return {"ok": ok, "checks": checks, "dir": d}


@pytest.fixture(scope="module")
def monkeypatch_module():
    from _pytest.monkeypatch import MonkeyPatch

    mp = MonkeyPatch()
    yield mp
    mp.undo()


def test_pipeline_runs_and_every_check_passes(warehouse):
    assert warehouse["ok"], warehouse["checks"]
    assert set(warehouse["checks"]) == {"silver_has_no_personal_data", "gold_systems_registered", "layers_reconcile"}
    assert all(warehouse["checks"].values())


def test_bronze_keeps_what_it_got_and_silver_does_not(warehouse):
    from provenance.data import lakehouse

    bronze = "\n".join(lakehouse.read_arrow("bronze", "evidence").column("summary").to_pylist())
    silver = "\n".join(lakehouse.read_arrow("silver", "evidence").column("summary").to_pylist())
    for planted in PLANTED:
        assert planted in bronze, planted
        assert planted not in silver, planted
    assert "<PERSON>" in silver and "<EMAIL>" in silver and "<IP>" in silver
    clean = "IAM policy binding change reviewed and approved via change CR-4471"
    assert clean in silver  # a row with nothing to redact is untouched


def test_gold_is_the_narrow_typed_view_and_loads_without_a_catalog(warehouse):
    import pyarrow as pa

    from provenance.data import lakehouse
    from provenance.data.assets import SCHEMA

    gold = lakehouse.read_arrow("gold", "evidence")
    assert gold.schema.names == SCHEMA.names
    assert pa.types.is_timestamp(gold.schema.field("observed_at").type)
    assert set(gold.column("system_id").to_pylist()) == {"sys-windrow-prod", "sys-windrow-dev"}
    for planted in PLANTED:
        assert planted not in "\n".join(gold.column("summary").to_pylist())
    static = lakehouse.load_static("gold", "evidence")
    assert [f.name for f in static.spec().fields] == ["system_id"]  # partitioned by system
    con = static.scan().to_duckdb("gold")
    assert con.execute("select count(*) from gold where system_id = 'sys-windrow-prod'").fetchone()[0] >= 9


def test_redactor_is_narrow_on_purpose():
    from provenance.data.redact import find, find_patterns, redact

    # the check's independent layer: patterns only, no language model
    assert find_patterns("paged at +1 415 555 0142, see jane.doe@windrow-corp.com at 10.20.30.40") == ["EMAIL_ADDRESS", "IP_ADDRESS", "PHONE_NUMBER"]
    assert find_patterns("control 3.1.1 reviewed via CR-4471 on 2026-09-01") == []

    assert find("Workload identity pool restricts CI to repo deathscythe272/blackfork-platform") == []
    # the platform's own vocabulary is not a person (ev-0004 lost "Suricata" before the allow list)
    suricata = "Suricata alert ET SCAN Nmap Scripting Engine detected and forwarded to SIEM within 3s"
    assert redact(suricata).text == suricata
    r = redact("Approved by Jane Doe (jane.doe@windrow-corp.com) from 10.20.30.40")
    assert r.text == "Approved by <PERSON> (<EMAIL>) from <IP>"
    assert sorted(r.entities) == ["EMAIL_ADDRESS", "IP_ADDRESS", "PERSON"]


def test_evidence_store_serves_gold_from_the_pointer_and_falls_back(warehouse, tmp_path):
    """The evidence server's store: gold when the pointer exists, the baked file when not."""
    import duckdb

    from provenance.evidence_mcp.store import open_store

    wh = (warehouse["dir"] / "warehouse").as_uri()
    store = open_store({"LAKEHOUSE_WAREHOUSE": wh})
    assert store.source.startswith("gold:") and store.rows == 16
    ts = store.con.execute("select observed_at from evidence order by observed_at limit 1").fetchone()[0]
    assert ts.tzinfo is None and ts.year == 2026  # read back without any time-zone library
    summaries = "\n".join(r[0] for r in store.con.execute("select summary from evidence where control_id = '3.5.2'").fetchall())
    for planted in PLANTED:
        assert planted not in summaries
    assert "<PERSON>" in summaries

    baked = tmp_path / "evidence.duckdb"
    con = duckdb.connect(str(baked)); con.execute("create table evidence as select 'ev-x' as row_id, 'sys-windrow-prod' as system_id"); con.close()
    store = open_store({"LAKEHOUSE_WAREHOUSE": (tmp_path / "empty").as_uri(), "EVIDENCE_DB": str(baked)})
    assert store.source.startswith("baked:") and store.rows == 1
