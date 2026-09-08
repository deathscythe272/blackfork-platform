"""The evidence pipeline as Dagster assets: bronze, silver, gold, and the checks that
make each layer's promise testable.

  bronze_evidence   the source rows as received (today the fixture CSV; later the
                    collectors), written verbatim
  silver_evidence   bronze with the free-text field redacted; a check re-scans silver
                    and fails the run if any personal data survived
  gold_evidence     the narrow, typed view the evidence server serves, partitioned by
                    system; checks that every row's system is registered and that the
                    three layers hold the same rows

Serves: BR-1, BR-2, BR-7.
"""


import os
import pathlib

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.csv as pacsv
import yaml
from dagster import AssetCheckResult, AssetExecutionContext, Definitions, MaterializeResult, asset, asset_check

from provenance.data import lakehouse
from provenance.data.redact import find, find_patterns, redact

HERE = pathlib.Path(__file__).resolve().parent
REGISTRY = HERE / "systems.yml"
FREE_TEXT = ["summary"]  # the only column a person writes into; everything else is an identifier

SCHEMA = pa.schema([
    ("row_id", pa.string()), ("system_id", pa.string()), ("control_id", pa.string()),
    ("control_name", pa.string()), ("framework", pa.string()), ("source", pa.string()),
    ("observed_at", pa.timestamp("us", tz="UTC")), ("summary", pa.string()), ("evidence_ref", pa.string()),
])


def source_csv() -> pathlib.Path:
    return pathlib.Path(os.environ.get("EVIDENCE_SOURCE_CSV") or (HERE.parent / "fixtures" / "evidence.csv"))


def registered_systems() -> set[str]:
    return {s["system_id"] for s in yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))["systems"]}


@asset(group_name="lakehouse", description="Evidence rows exactly as received.")
def bronze_evidence(context: AssetExecutionContext) -> MaterializeResult:
    raw = pacsv.read_csv(source_csv(), convert_options=pacsv.ConvertOptions(
        column_types={f.name: (pa.string() if f.name != "observed_at" else pa.timestamp("s", tz="UTC")) for f in SCHEMA}))
    table = raw.select([f.name for f in SCHEMA]).cast(SCHEMA)
    lakehouse.write_table("bronze", "evidence", table)
    context.log.info("bronze: %d rows from %s", table.num_rows, source_csv())
    return MaterializeResult(metadata={"rows": table.num_rows, "source": str(source_csv())})


@asset(group_name="lakehouse", deps=[bronze_evidence], description="Bronze with personal data redacted before storage (ADR-006).")
def silver_evidence(context: AssetExecutionContext) -> MaterializeResult:
    table = lakehouse.read_arrow("bronze", "evidence")
    hits = 0
    columns = {}
    for name in table.column_names:
        if name in FREE_TEXT:
            redacted = [redact(v) for v in table.column(name).to_pylist()]
            hits += sum(len(r.entities) for r in redacted)
            columns[name] = pa.array([r.text for r in redacted], pa.string())
        else:
            columns[name] = table.column(name)
    silver = pa.table(columns).cast(SCHEMA)
    lakehouse.write_table("silver", "evidence", silver)
    context.log.info("silver: %d rows, %d redactions", silver.num_rows, hits)
    return MaterializeResult(metadata={"rows": silver.num_rows, "redactions": hits})


@asset_check(asset=silver_evidence, description="Re-scan silver two ways: no personal data may survive redaction.")
def silver_has_no_personal_data() -> AssetCheckResult:
    """Two detectors, on purpose: the redactor's own, and a plain-pattern layer that
    does not share its blind spots. Either one finding anything fails the run."""
    silver = lakehouse.read_arrow("silver", "evidence")
    survivors = {}
    for name in FREE_TEXT:
        values = silver.column(name).to_pylist()
        survivors[name] = {"model": sum(len(find(v)) for v in values), "patterns": sum(len(find_patterns(v)) for v in values)}
    total = sum(sum(v.values()) for v in survivors.values())
    return AssetCheckResult(passed=total == 0, metadata={"survivors": survivors})


@asset(group_name="lakehouse", deps=[silver_evidence], description="The narrow view the evidence server serves, by system.")
def gold_evidence(context: AssetExecutionContext) -> MaterializeResult:
    silver = lakehouse.read_arrow("silver", "evidence")
    gold = silver.sort_by([("system_id", "ascending"), ("row_id", "ascending")])
    lakehouse.write_table("gold", "evidence", gold, partition_by="system_id")
    systems = pc.unique(gold.column("system_id")).to_pylist()
    context.log.info("gold: %d rows across %s", gold.num_rows, systems)
    return MaterializeResult(metadata={"rows": gold.num_rows, "systems": sorted(systems)})


@asset_check(asset=gold_evidence, description="Every gold row names a registered system.")
def gold_systems_registered() -> AssetCheckResult:
    gold = lakehouse.read_arrow("gold", "evidence")
    unknown = sorted(set(gold.column("system_id").to_pylist()) - registered_systems())
    return AssetCheckResult(passed=not unknown, metadata={"unregistered": unknown})


@asset_check(asset=gold_evidence, description="Bronze, silver, and gold hold the same rows.")
def layers_reconcile() -> AssetCheckResult:
    ids = {layer: set(lakehouse.read_arrow(layer, "evidence").column("row_id").to_pylist()) for layer in ("bronze", "silver", "gold")}
    same = ids["bronze"] == ids["silver"] == ids["gold"]
    return AssetCheckResult(passed=same, metadata={layer: len(v) for layer, v in ids.items()})


ASSETS = [bronze_evidence, silver_evidence, gold_evidence]
CHECKS = [silver_has_no_personal_data, gold_systems_registered, layers_reconcile]
defs = Definitions(assets=ASSETS, asset_checks=CHECKS)
