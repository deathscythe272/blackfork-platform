"""The investigation workflow: a finding in, a ranked and explained verdict out.

    python -m provenance.agent.assess sys-windrow-prod 3.3.1

For one control on one system: read the requirement and the evidence through the
gateway as the Control Mapper's identity, have the mapper draft its statement, assemble
the finding, and send it to the Risk Analyst, a separate service with its own key that
never touches the door. The workflow holds the mapper's job token; the analyst holds
nothing (ADR-004). Serves: BR-3, BR-8.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any

from provenance.agent.mapper import main as mapper_main
from provenance.risk_analyst.client import send_finding


async def _gateway_call(tool: str, args: dict[str, Any], token: str) -> Any:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    url = os.environ.get("GATEWAY_URL", "http://localhost:8000/mcp")
    async with streamablehttp_client(url, headers={"X-Agent-Token": token}) as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            res = await s.call_tool(tool, args)
            if res.isError:
                raise RuntimeError("; ".join(getattr(c, "text", "") for c in res.content))
            if res.structuredContent is not None:
                sc = res.structuredContent
                return sc.get("result", sc) if isinstance(sc, dict) else sc
            return [json.loads(c.text) for c in res.content if getattr(c, "text", None)]


async def main(system_id: str, control_id: str, token: str | None = None) -> dict[str, Any]:
    token = token or os.environ["GATEWAY_TOKEN"]
    control = await _gateway_call("get_control", {"framework": "800-171", "control_id": control_id}, token)
    evidence = await _gateway_call("get_evidence", {"system_id": system_id, "control_id": control_id, "limit": 50}, token)
    mapped = await mapper_main(system_id, control_id, token=token)
    finding = {
        "system_id": system_id, "control_id": control_id,
        "requirement": (control or {}).get("statement", "") if isinstance(control, dict) else "",
        "statement": mapped.get("answer") or "",
        "evidence": [{k: r.get(k) for k in ("row_id", "source", "observed_at", "summary")} for r in (evidence or [])],
    }
    verdict = send_finding(finding, identity="control-mapper")
    return {**mapped, "finding_rows": [r["row_id"] for r in finding["evidence"]], "verdict": verdict,
            "answer": f"{mapped.get('answer') or ''}\n\nVerdict: {verdict['severity']} ({verdict['score']}/100). {verdict['explanation']}"}


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(2)
    print("\n=== RESULT ===")
    print(json.dumps(asyncio.run(main(sys.argv[1], sys.argv[2])), indent=2))
