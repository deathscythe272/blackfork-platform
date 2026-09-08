"""Where the controls server's rows come from: the data plane's gold controls table
from its pointer when it exists, otherwise the catalog file baked into the image,
rendered with the organization's parameter values. Same shape either way.

Serves: BR-2, BR-7.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

import duckdb

log = logging.getLogger("controls-mcp")

COLUMNS = ["framework", "revision", "control_id", "legacy_id", "family_id", "family", "title", "status",
           "statement", "guidance", "objectives", "parameters"]


@dataclass
class Store:
    con: duckdb.DuckDBPyConnection
    source: str
    rows: int


def _from_rows(rows: list[dict]) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(database=":memory:")
    con.execute("CREATE TABLE controls (" + ", ".join(f"{c} VARCHAR" for c in COLUMNS) + ")")
    con.executemany("INSERT INTO controls VALUES (" + ", ".join("?" for _ in COLUMNS) + ")",
                    [[r.get(c, "") for c in COLUMNS] for r in rows])
    return con


def _load_gold(warehouse: str) -> Store | None:
    from provenance.data import lakehouse

    try:
        table = lakehouse.load_static("gold", "controls", root=warehouse)
    except FileNotFoundError as e:
        log.warning("no gold controls at %s (%s); rendering the baked catalog", warehouse, e)
        return None
    arrow = table.scan().to_arrow()
    con = duckdb.connect(database=":memory:")
    con.register("gold_arrow", arrow)
    con.execute("CREATE TABLE controls AS SELECT * FROM gold_arrow")
    con.unregister("gold_arrow")
    return Store(con, f"gold:{lakehouse.pointer_url('gold', 'controls', warehouse)}", arrow.num_rows)


def open_store(env: dict[str, str] | None = None) -> Store:
    env = os.environ if env is None else env
    warehouse = env.get("LAKEHOUSE_WAREHOUSE")
    store = _load_gold(warehouse) if warehouse else None
    if store is None:
        from provenance.data.catalog import rows

        data = rows("800-171")
        store = Store(_from_rows(data), "baked:NIST_SP800-171_rev3_catalog-min.json + odp/blackfork.yml", len(data))
    log.info("serving %d controls from %s", store.rows, store.source)
    return store
