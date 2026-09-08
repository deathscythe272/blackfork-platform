"""How another agent asks the Risk Analyst for a verdict: over the A2A shape, with a
token for the caller's identity signed by the analyst's own key. The caller assembles
the finding from what it read through the gateway; the analyst never reads the door.

Serves: BR-3, BR-8.
"""

from __future__ import annotations

import os
import uuid
from typing import Any

import httpx

from provenance.gateway.tokens import mint
from provenance.gateway.upstream import UpstreamIdentity

# In the cloud the analyst's door is closed at the platform level too: only the agent
# service's identity may invoke it, so the call carries a signed identity token for the
# analyst's address (RISK_ANALYST_AUDIENCE) as well as the analyst's own X-Analyst-Token.
_IDENTITY = UpstreamIdentity(os.environ.get("RISK_ANALYST_AUDIENCE") or None)


def analyst_url() -> str:
    return os.environ.get("RISK_ANALYST_URL", "http://localhost:8090").rstrip("/")


def caller_token(identity: str) -> str:
    key = os.environ.get("RISK_SIGNING_KEY", "")
    return mint(identity, ttl_seconds=600, key=key)


def send_finding(finding: dict[str, Any], identity: str = "control-mapper", timeout: float = 120.0) -> dict[str, Any]:
    """message/send to the analyst; returns the verdict from the task's artifact."""
    rpc = {"jsonrpc": "2.0", "id": str(uuid.uuid4()), "method": "message/send",
           "params": {"message": {"role": "user", "messageId": str(uuid.uuid4()),
                                  "parts": [{"kind": "data", "data": finding}]}}}
    headers = {"X-Analyst-Token": caller_token(identity), **_IDENTITY.headers()}
    r = httpx.post(f"{analyst_url()}/a2a", json=rpc, headers=headers, timeout=timeout)
    body = r.json()
    if r.status_code != 200 or "error" in body:
        raise RuntimeError(f"risk analyst HTTP {r.status_code}: {body.get('error')}")
    task = body["result"]
    return next(p["data"] for a in task["artifacts"] for p in a["parts"] if p.get("kind") == "data")
