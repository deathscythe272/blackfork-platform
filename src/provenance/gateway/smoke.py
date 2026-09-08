"""Gateway smoke test: three calls through the door, no agent involved.

  1. allowed  - evidence-collector asks for its own system      -> rows come back
  2. denied   - evidence-collector asks for another system      -> policy denial, audited
  3. spoofed  - a forged token asks for anything                 -> identity rejection, audited

Exit code is non-zero if any expectation fails. Serves: BR-7, BR-8 (T1-GW-01, T1-GW-06).
"""

from __future__ import annotations

import asyncio
import json
import os
import pathlib
import sys

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from provenance.gateway.tokens import mint

GATEWAY_URL = os.environ.get("GATEWAY_URL", "http://localhost:8000/mcp")
AUDIT_LOG = pathlib.Path(os.environ.get("AUDIT_LOG", "audit/audit.jsonl"))


async def call(token: str, tool: str, args: dict) -> tuple[bool, str]:
    headers = {"X-Agent-Token": token}
    async with streamablehttp_client(GATEWAY_URL, headers=headers) as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            res = await s.call_tool(tool, args)
    text = json.dumps(res.structuredContent) if res.structuredContent else "; ".join(getattr(c, "text", "") for c in res.content)
    return (not res.isError), text


async def main() -> int:
    before = AUDIT_LOG.read_text(encoding="utf-8").count("\n") if AUDIT_LOG.exists() else 0
    good = mint("evidence-collector")
    forged = mint("evidence-collector", key="x" * 48)  # signed with the wrong key
    failures = []

    ok, text = await call(good, "get_evidence", {"system_id": "sys-windrow-prod", "control_id": "3.3.1"})
    print("1 allowed :", "OK" if ok else "ERROR", text[:160])
    if not ok or "ev-0003" not in text:
        failures.append("allowed call did not return prod evidence")

    ok, text = await call(good, "get_evidence", {"system_id": "sys-windrow-dev", "control_id": "3.3.1"})
    print("2 denied  :", "DENIED" if not ok else "UNEXPECTED ALLOW", text[:160])
    if ok or "denied by policy" not in text:
        failures.append("cross-system call was not denied by policy")

    ok, text = await call(forged, "list_controls", {"system_id": "sys-windrow-prod"})
    print("3 spoofed :", "REJECTED" if not ok else "UNEXPECTED ALLOW", text[:160])
    if ok or "identity rejected" not in text:
        failures.append("forged token was not rejected")

    lines = AUDIT_LOG.read_text(encoding="utf-8").splitlines()[before:]
    rows = [json.loads(line) for line in lines]
    decisions = [(r["identity"], r["decision"], r["reason"]) for r in rows]
    print("audit rows:", *decisions, sep="\n  ")
    if len(rows) != 3 or [r["decision"] for r in rows] != ["allow", "deny", "deny"]:
        failures.append(f"expected 3 audit rows allow/deny/deny, got {[r['decision'] for r in rows]}")

    for f in failures:
        print("FAIL:", f)
    print("smoke:", "PASS" if not failures else "FAIL")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
