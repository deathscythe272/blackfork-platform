"""evidence-mcp: parameterized, read-only tools over the Gold `evidence` view.

The rows come from the data plane's gold table, loaded from its pointer at startup
(store.py); the fixture baked into the image is the fallback for a deploy that runs
before the pipeline has.

Three tools, every one of them scoped by `system_id`. There is no free-form query
tool on purpose: the shape of what an agent may ask is part of the security boundary
(ADR-003). This server is reachable only from the gateway (ADR-001); it does
no authentication of its own because nothing but the gateway can reach its network.

Serves: BR-2, BR-7, BR-8.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from provenance.evidence_mcp.store import open_store

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
HOST = os.environ.get("EVIDENCE_MCP_HOST", "0.0.0.0")
PORT = int(os.environ.get("EVIDENCE_MCP_PORT", "8001"))

mcp = FastMCP("evidence-mcp", host=HOST, port=PORT)
_STORE = None


def _store():
    """Opened on first use, not at import, so tools and tests can import this module."""
    global _STORE
    if _STORE is None:
        _STORE = open_store()
    return _STORE


def _query(sql: str, params: list[Any]) -> list[dict[str, Any]]:
    cur = _store().con.cursor()  # one connection, a cursor per call; the store is read only
    try:
        cur.execute(sql, params)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, (str(v) if hasattr(v, "isoformat") else v for v in row))) for row in cur.fetchall()]
    finally:
        cur.close()


@mcp.tool()
def list_controls(system_id: str) -> list[dict[str, Any]]:
    """List the controls that have evidence for one system, with evidence counts."""
    return _query(
        """
        SELECT control_id, control_name, framework, count(*) AS evidence_count
        FROM evidence WHERE system_id = ?
        GROUP BY control_id, control_name, framework ORDER BY control_id
        """,
        [system_id],
    )


@mcp.tool()
def get_evidence(system_id: str, control_id: str, limit: int = 10) -> list[dict[str, Any]]:
    """Return evidence rows for one control on one system, newest first."""
    limit = max(1, min(int(limit), 50))
    return _query(
        """
        SELECT row_id, system_id, control_id, source, observed_at, summary, evidence_ref
        FROM evidence WHERE system_id = ? AND control_id = ?
        ORDER BY observed_at DESC LIMIT ?
        """,
        [system_id, control_id, limit],
    )


@mcp.tool()
def get_evidence_row(system_id: str, row_id: str) -> dict[str, Any] | None:
    """Return one evidence row by id. The row must belong to the given system."""
    rows = _query(
        "SELECT * FROM evidence WHERE system_id = ? AND row_id = ?",
        [system_id, row_id],
    )
    return rows[0] if rows else None


if __name__ == "__main__":
    _store()  # load before serving so the first caller does not pay for it, and a bad warehouse fails loudly
    mcp.run(transport="streamable-http")
