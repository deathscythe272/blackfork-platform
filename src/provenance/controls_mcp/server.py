"""controls-mcp: parameterized, read-only tools over the control catalogs.

Three tools, every one scoped by `framework`; there is no free-form query on purpose
(ADR-003). Rows come from the data plane's gold controls table when its pointer exists
(store.py), otherwise from the catalog file baked into the image, rendered with the
organization's parameter values. Reachable only through the gateway (ADR-001).

Serves: BR-2, BR-7, BR-8.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from provenance.controls_mcp.store import open_store
from provenance.data.catalog import FRAMEWORKS, normalize_id

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
HOST = os.environ.get("CONTROLS_MCP_HOST", "0.0.0.0")
PORT = int(os.environ.get("CONTROLS_MCP_PORT", "8002"))

mcp = FastMCP("controls-mcp", host=HOST, port=PORT)
_STORE = None


def _store():
    global _STORE
    if _STORE is None:
        _STORE = open_store()
    return _STORE


def _framework(framework: str) -> str:
    if framework not in FRAMEWORKS:
        raise ValueError(f"unknown framework {framework!r}; known: {sorted(FRAMEWORKS)}")
    return framework


def _query(sql: str, params: list[Any]) -> list[dict[str, Any]]:
    cur = _store().con.cursor()
    try:
        cur.execute(sql, params)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        cur.close()


@mcp.tool()
def get_control(framework: str, control_id: str) -> dict[str, Any] | None:
    """One control's statement, guidance, and assessment objectives. framework is the id, exactly "800-171"; control_id accepts `3.3.1` or `03.03.01`."""
    rows = _query(
        "SELECT framework, revision, control_id, legacy_id, family, title, status, statement, guidance, objectives "
        "FROM controls WHERE framework = ? AND control_id = ?",
        [_framework(framework), normalize_id(control_id)],
    )
    return rows[0] if rows else None


@mcp.tool()
def list_family(framework: str, family_id: str) -> list[dict[str, Any]]:
    """The controls in one family (for example `03.03`, Audit and Accountability), with status. framework is the id, exactly "800-171"."""
    return _query(
        "SELECT control_id, legacy_id, title, status FROM controls WHERE framework = ? AND family_id = ? ORDER BY control_id",
        [_framework(framework), normalize_id(family_id)],
    )


@mcp.tool()
def search_controls(framework: str, query: str, limit: int = 10) -> list[dict[str, Any]]:
    """Active controls whose title or statement contains the words given. framework is the id, exactly "800-171"."""
    limit = max(1, min(int(limit), 25))
    words = [w.lower() for w in query.split() if len(w) > 2][:6]
    if not words:
        return []
    where = " AND ".join("(lower(title) LIKE ? OR lower(statement) LIKE ?)" for _ in words)
    params: list[Any] = [_framework(framework)]
    for w in words:
        params += [f"%{w}%", f"%{w}%"]
    return _query(
        f"SELECT control_id, legacy_id, family, title FROM controls WHERE framework = ? AND status = 'active' AND {where} "
        f"ORDER BY control_id LIMIT {limit}",
        params,
    )


if __name__ == "__main__":
    _store()
    mcp.run(transport="streamable-http")
