"""Checks against the deployed slice, no model in the loop. Run from a laptop:

    GATEWAY_URL=https://<gateway>/mcp EVIDENCE_URL=https://<evidence> \\
    GATEWAY_SIGNING_KEY=<the value in Secret Manager> \\
    python -m provenance.evals.deployed_check

Each check carries the threat-model id it closes in the cloud form:

  T1-EV-01  the evidence server refuses a caller with no identity token; only the
            gateway's identity is granted the invoker right
  T1-GW-01  the gateway refuses a forged token
  T1-GW-02  the gateway denies a valid identity asking for another system's rows

Writes results/deployed-check.json. Exit code 1 on any failure. Serves: BR-7, BR-8.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
import pathlib
import sys

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from provenance.gateway.tokens import mint

HERE = pathlib.Path(__file__).resolve().parent
GATEWAY_URL = os.environ["GATEWAY_URL"]
EVIDENCE_URL = os.environ["EVIDENCE_URL"]


def _gateway_call(tool: str, args: dict, token: str) -> tuple[bool, str]:
    async def go():
        async with streamablehttp_client(GATEWAY_URL, headers={"Authorization": f"Bearer {token}"}) as (r, w, _):
            async with ClientSession(r, w) as s:
                await s.initialize()
                res = await s.call_tool(tool, args)
                text = "; ".join(getattr(c, "text", "") for c in res.content)
                return (not res.isError), text

    return asyncio.run(go())


def main() -> int:
    checks = []

    # T1-EV-01: the evidence door admits no anonymous caller.
    r = httpx.post(f"{EVIDENCE_URL}/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize"},
                   headers={"Accept": "application/json, text/event-stream"}, timeout=30)
    checks.append({"id": "T1-EV-01", "what": "evidence server without an identity token",
                   "passed": r.status_code in (401, 403), "detail": f"HTTP {r.status_code}"})

    # T1-GW-01: a token signed with the wrong key is refused at the gateway.
    real_key = os.environ.get("GATEWAY_SIGNING_KEY")
    os.environ["GATEWAY_SIGNING_KEY"] = "not-the-real-key"
    forged = mint("evidence-collector")
    if real_key:
        os.environ["GATEWAY_SIGNING_KEY"] = real_key
    ok, text = _gateway_call("list_controls", {"system_id": "sys-windrow-prod"}, forged)
    checks.append({"id": "T1-GW-01", "what": "gateway with a forged token",
                   "passed": (not ok) and "identity rejected" in text, "detail": text[:160]})

    # With the real key: a valid identity is denied another system's rows and allowed its own.
    if real_key:
        ok, text = _gateway_call("get_evidence", {"system_id": "sys-other-corp", "control_id": "AU-2"},
                                 mint("evidence-collector"))
        checks.append({"id": "T1-GW-02", "what": "valid identity, other system's rows",
                       "passed": (not ok) and "denied by policy" in text, "detail": text[:160]})
        ok, text = _gateway_call("list_controls", {"system_id": "sys-windrow-prod"}, mint("evidence-collector"))
        checks.append({"id": "allowed-path", "what": "valid identity, own system, gateway to evidence and back",
                       "passed": ok, "detail": text[:160]})

    report = {"run_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
              "gateway": GATEWAY_URL, "evidence": EVIDENCE_URL, "checks": checks}
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results" / "deployed-check.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    for c in checks:
        print(f"{'PASS' if c['passed'] else 'FAIL'}  {c['id']:10s} {c['what']}: {c['detail']}")
    return 0 if all(c["passed"] for c in checks) else 1


if __name__ == "__main__":
    sys.exit(main())
