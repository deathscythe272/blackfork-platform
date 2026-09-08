"""Where the evidence server's rows come from.

Preferred: the gold table the data plane published, loaded from its pointer with no
catalog (ADR-002): a folder on the laptop, the lakehouse bucket in the cloud, chosen by
LAKEHOUSE_WAREHOUSE. The rows are read once into an in-memory DuckDB and served from
there; the server holds no write path to the table and its cloud identity has bucket
read only (T1-EV-03).

Fallback: the fixture rows baked into the image at EVIDENCE_DB, so a fresh deploy
answers before the pipeline has ever run. The server logs which one it is serving.

Serves: BR-2, BR-7.
"""

from __future__ import annotations

import logging
import os
import pathlib
from dataclasses import dataclass

import duckdb
import pyarrow as pa

log = logging.getLogger("evidence-mcp")


@dataclass
class Store:
    con: duckdb.DuckDBPyConnection
    source: str  # "gold:<pointer url>" or "baked:<path>"
    rows: int


def _load_gold(warehouse: str) -> Store | None:
    from provenance.data import lakehouse  # pyiceberg and the file layers; only needed on this path

    try:
        table = lakehouse.load_static("gold", "evidence", root=warehouse)
    except FileNotFoundError as e:
        log.warning("no gold table at %s (%s); falling back to the baked fixture", warehouse, e)
        return None
    arrow = table.scan().to_arrow()
    # Gold stores observed_at as an instant with a zone. Serve it as a plain UTC timestamp,
    # the shape the baked fixture always had: DuckDB hands zoned values back only through
    # an extra library the service image does not carry, which the first gold read in a
    # container found out the hard way.
    for i, field in enumerate(arrow.schema):
        if pa.types.is_timestamp(field.type) and field.type.tz is not None:
            arrow = arrow.set_column(i, field.name, arrow.column(i).cast(pa.timestamp(field.type.unit)))
    con = duckdb.connect(database=":memory:")
    con.register("gold_arrow", arrow)
    con.execute("CREATE TABLE evidence AS SELECT * FROM gold_arrow")
    con.unregister("gold_arrow")
    return Store(con, f"gold:{lakehouse.pointer_url('gold', 'evidence', warehouse)}", arrow.num_rows)


def _load_baked(path: pathlib.Path) -> Store:
    con = duckdb.connect(str(path), read_only=True)
    rows = con.execute("SELECT count(*) FROM evidence").fetchone()[0]
    return Store(con, f"baked:{path}", rows)


def open_store(env: dict[str, str] | None = None) -> Store:
    env = os.environ if env is None else env
    warehouse = env.get("LAKEHOUSE_WAREHOUSE")
    store = _load_gold(warehouse) if warehouse else None
    if store is None:
        store = _load_baked(pathlib.Path(env.get("EVIDENCE_DB", "data/evidence.duckdb")))
    log.info("serving %d evidence rows from %s", store.rows, store.source)
    return store


def control_id_variants(control_id: str) -> list[str]:
    """The same control in every numbering the platform meets: `3.3.1` as the evidence
    rows carry it, `03.03.01` as the current catalog names it. The Control Mapper read a
    control from the catalog, asked for its evidence under the catalog's numbering, and
    got nothing; a control is one thing however it is written."""
    from provenance.data.catalog import legacy_id, normalize_id

    cid = control_id.strip()
    out = [cid]
    for v in (legacy_id(cid), normalize_id(cid)):
        if v not in out:
            out.append(v)
    return out
