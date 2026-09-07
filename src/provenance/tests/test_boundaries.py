"""Boundary tests at the door, against the running Compose stack. No model in the loop.

Each test carries the threat-model id it closes. Run with the stack up:

    docker compose up -d opa evidence-mcp gateway otel-collector
    GATEWAY_SIGNING_KEY=<from .env> pytest src/provenance/tests -q

Serves: BR-7, BR-8. Tests: T1-EV-01, T1-EV-02, T1-EV-03, T1-GW-04, T1-PL-03.
"""

from __future__ import annotations

import asyncio
import json
import os
import pathlib
import subprocess
import time

import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from provenance.gateway.tokens import mint

ROOT = pathlib.Path(__file__).resolve().parents[3]
GATEWAY_URL = os.environ.get("GATEWAY_URL", "http://localhost:8000/mcp")
AUDIT_LOG = ROOT / "audit" / "audit.jsonl"

pytestmark = pytest.mark.skipif(not os.environ.get("GATEWAY_SIGNING_KEY"), reason="needs the Compose stack and GATEWAY_SIGNING_KEY")


def _compose(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", "compose", *args], cwd=ROOT, capture_output=True, text=True)


def _call(tool: str, args: dict, identity: str = "evidence-collector") -> tuple[bool, str]:
    async def go():
        headers = {"Authorization": f"Bearer {mint(identity)}"}
        async with streamablehttp_client(GATEWAY_URL, headers=headers) as (r, w, _):
            async with ClientSession(r, w) as s:
                await s.initialize()
                res = await s.call_tool(tool, args)
        text = json.dumps(res.structuredContent) if res.structuredContent else "; ".join(getattr(c, "text", "") for c in res.content)
        return (not res.isError), text
    return asyncio.run(go())


def test_t1_ev_01_agent_cannot_resolve_evidence_server():
    """T1-EV-01: from the agent container, evidence-mcp has no route."""
    probe = "import socket\ntry:\n    socket.getaddrinfo('evidence-mcp', 8001); print('REACHABLE')\nexcept OSError: print('UNREACHABLE')"
    r = _compose("run", "--rm", "-T", "agent", "python", "-c", probe)
    assert "UNREACHABLE" in r.stdout, r.stdout + r.stderr


def test_t1_ev_02_row_from_another_system_returns_nothing():
    """T1-EV-02: a row id from another system, asked under the allowed system, is empty."""
    ok, text = _call("get_evidence_row", {"system_id": "sys-windrow-prod", "row_id": "ev-0102"})
    assert ok, text
    assert "ev-0102" not in text and "sys-windrow-dev" not in text
    assert text.strip() in ("", "null", "None", "{}", "[null]", "[]") or ("result" in text and "null" in text)


def test_t1_ev_03_evidence_server_is_read_only():
    """T1-EV-03: the evidence server's connection cannot write."""
    from provenance.evidence_mcp import server

    with pytest.raises(Exception):
        server._query("INSERT INTO evidence (row_id, system_id) VALUES ('ev-9999', 'sys-windrow-prod')", [])


def test_t1_gw_04_audit_and_logs_carry_no_payloads():
    """T1-GW-04: an allowed call's audit row holds identifiers only; gateway logs hold no result text."""
    ok, text = _call("get_evidence", {"system_id": "sys-windrow-prod", "control_id": "3.3.1"})
    assert ok and "ev-0003" in text
    last = json.loads(AUDIT_LOG.read_text(encoding="utf-8").splitlines()[-1])
    assert set(last["args"]) == {"system_id", "control_id", "limit"}
    assert "summary" not in json.dumps(last) and "evidence_ref" not in json.dumps(last)
    logs = _compose("logs", "--no-log-prefix", "gateway").stdout
    assert "Admin activity and data access logs" not in logs  # a summary string from the fixture


def test_t1_pl_03_gateway_fails_closed_without_opa():
    """T1-PL-03: with the policy engine down, calls are refused and nothing is forwarded."""
    _compose("stop", "opa")
    try:
        time.sleep(1)
        before = len(AUDIT_LOG.read_text(encoding="utf-8").splitlines())
        ok, text = _call("list_controls", {"system_id": "sys-windrow-prod"})
        assert not ok and "failing closed" in text, text
        after = len(AUDIT_LOG.read_text(encoding="utf-8").splitlines())
        assert after == before  # no decision, no forward, and nothing written as if decided
    finally:
        _compose("start", "opa")
        time.sleep(2)
    ok, _ = _call("list_controls", {"system_id": "sys-windrow-prod"})
    assert ok
