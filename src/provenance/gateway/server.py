"""The auth and audit gateway (ADR-001), as an MCP server the agent talks to.

The gateway mirrors the three evidence tools. On every call, in this order:

  1. verify identity   - signed token in the X-Agent-Token header -> agent identity
                         (Authorization: Bearer is accepted too, for the laptop; the
                         cloud front door claims that header for its own tokens)
  2. validate request  - FastMCP validates arguments against the tool schema before
                         this code runs; unknown tools never reach us
  3. ask OPA           - identity + tool + args -> allow/deny, reason, policy version
  4. write audit row   - denied calls included; written BEFORE forwarding; if the
                         write fails the call fails. The sink is a file on the laptop
                         and the platform-events topic in the cloud (audit.py)
  5. forward           - allowed calls go to the server that owns the tool, evidence-mcp
                         or controls-mcp, over MCP; the result is returned unchanged. In
                         the cloud the call carries the gateway's signed identity
                         (upstream.py)

Fail closed: if the token is bad, OPA is unreachable, or the audit write fails, the
agent gets an error, never data.

Serves: BR-7, BR-8.
"""

from __future__ import annotations

import datetime as dt
import os
import time
import uuid
from typing import Any

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from provenance.gateway.audit import AuditWriteError, sink_from_env
from provenance.gateway.tokens import IdentityError, verify
from provenance.gateway.upstream import identity_from_env

HOST = os.environ.get("GATEWAY_HOST", "0.0.0.0")
PORT = int(os.environ.get("GATEWAY_PORT", "8000"))
OPA_URL = os.environ.get("OPA_URL", "http://localhost:8181")

mcp = FastMCP("blackfork-gateway", host=HOST, port=PORT)
AUDIT = sink_from_env()

# Every tool belongs to exactly one upstream server. A tool absent here cannot be
# forwarded even if policy allowed it, which it also cannot (policy lists the same tools).
UPSTREAMS = {
    "evidence": {"url": os.environ.get("EVIDENCE_MCP_URL", "http://localhost:8001/mcp"),
                 "identity": identity_from_env(env={"EVIDENCE_MCP_AUDIENCE": os.environ.get("EVIDENCE_MCP_AUDIENCE", "")})},
    "controls": {"url": os.environ.get("CONTROLS_MCP_URL", "http://localhost:8002/mcp"),
                 "identity": identity_from_env(env={"EVIDENCE_MCP_AUDIENCE": os.environ.get("CONTROLS_MCP_AUDIENCE", "")})},
}
TOOL_UPSTREAM = {"list_controls": "evidence", "get_evidence": "evidence", "get_evidence_row": "evidence",
                 "get_control": "controls", "list_family": "controls", "search_controls": "controls"}


# --- 1. identity -----------------------------------------------------------------

TOKEN_HEADER = "x-agent-token"


def _identity(ctx: Context) -> str:
    """The agent's signed token. Preferred in X-Agent-Token, because the cloud front
    door inspects Authorization on every request and rejects tokens it did not issue
    before the gateway could see them. Authorization: Bearer still works on the laptop."""
    request = ctx.request_context.request
    if request is None:
        raise IdentityError("no request context")
    token = request.headers.get(TOKEN_HEADER, "").strip()
    if not token:
        header = request.headers.get("authorization", "")
        if not header.lower().startswith("bearer "):
            raise IdentityError("missing agent token")
        token = header[7:].strip()
    return verify(token)


# --- 3. policy -------------------------------------------------------------------

def _decide(identity: str, tool: str, args: dict[str, Any]) -> dict[str, Any]:
    payload = {"input": {"identity": identity, "tool": tool, "args": args}}
    try:
        r = httpx.post(f"{OPA_URL}/v1/data/blackfork/gateway/decision", json=payload, timeout=5.0)
        r.raise_for_status()
        result = r.json().get("result")
    except (httpx.HTTPError, ValueError) as e:
        raise ToolError(f"policy engine unavailable, failing closed: {e.__class__.__name__}") from e
    if not isinstance(result, dict) or "allow" not in result:
        raise ToolError("policy engine returned no decision, failing closed")
    return result


# --- 4. audit --------------------------------------------------------------------

def _audit(row: dict[str, Any]) -> None:
    try:
        AUDIT.write(row)
    except AuditWriteError as e:
        raise ToolError(f"audit write failed ({AUDIT.name}), failing closed: {e}") from e


# --- 5. forward ------------------------------------------------------------------

async def _forward(tool: str, args: dict[str, Any]) -> Any:
    upstream = UPSTREAMS[TOOL_UPSTREAM[tool]]
    async with streamablehttp_client(upstream["url"], headers=upstream["identity"].headers() or None) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool, args)
    if result.isError:
        text = "; ".join(getattr(c, "text", "") for c in result.content)
        raise ToolError(f"{TOOL_UPSTREAM[tool]}-mcp error: {text}")
    if result.structuredContent is not None:
        sc = result.structuredContent
        return sc.get("result", sc) if isinstance(sc, dict) else sc
    return [getattr(c, "text", None) for c in result.content]


# --- the pipeline ------------------------------------------------------------------

async def _guarded_call(ctx: Context, tool: str, args: dict[str, Any]) -> Any:
    started = time.perf_counter()
    call_id = str(uuid.uuid4())
    row: dict[str, Any] = {
        "id": call_id,
        "ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds"),
        "tool": tool,
        "args": args,
    }
    try:
        identity = _identity(ctx)
    except IdentityError as e:
        row.update(identity=None, decision="deny", reason=str(e), policy_version=None, forwarded=False)
        row["latency_ms"] = round((time.perf_counter() - started) * 1000, 1)
        _audit(row)
        raise ToolError(f"identity rejected: {e}") from e

    decision = _decide(identity, tool, args)
    allowed = bool(decision.get("allow"))
    row.update(
        identity=identity,
        decision="allow" if allowed else "deny",
        reason=decision.get("reason"),
        policy_version=decision.get("version"),
        forwarded=allowed,
    )
    row["latency_ms"] = round((time.perf_counter() - started) * 1000, 1)
    _audit(row)  # before forwarding, denies included

    if not allowed:
        raise ToolError(f"denied by policy ({decision.get('reason')}); this call has been logged")
    return await _forward(tool, args)


# --- the mirrored tools (same names and schemas as evidence-mcp) -------------------

@mcp.tool()
async def list_controls(system_id: str, ctx: Context) -> Any:
    """List the controls that have evidence for one system, with evidence counts."""
    return await _guarded_call(ctx, "list_controls", {"system_id": system_id})


@mcp.tool()
async def get_evidence(system_id: str, control_id: str, ctx: Context, limit: int = 10) -> Any:
    """Return evidence rows for one control on one system, newest first."""
    return await _guarded_call(ctx, "get_evidence", {"system_id": system_id, "control_id": control_id, "limit": limit})


@mcp.tool()
async def get_evidence_row(system_id: str, row_id: str, ctx: Context) -> Any:
    """Return one evidence row by id. The row must belong to the given system."""
    return await _guarded_call(ctx, "get_evidence_row", {"system_id": system_id, "row_id": row_id})


# --- the mirrored catalog tools (same names and schemas as controls-mcp) ------------

@mcp.tool()
async def get_control(framework: str, control_id: str, ctx: Context) -> Any:
    """One control's statement, guidance, and assessment objectives. framework is the id, exactly "800-171"; control_id accepts `3.3.1` or `03.03.01`."""
    return await _guarded_call(ctx, "get_control", {"framework": framework, "control_id": control_id})


@mcp.tool()
async def list_family(framework: str, family_id: str, ctx: Context) -> Any:
    """The controls in one family (for example `03.03`, Audit and Accountability), with status. framework is the id, exactly "800-171"."""
    return await _guarded_call(ctx, "list_family", {"framework": framework, "family_id": family_id})


@mcp.tool()
async def search_controls(framework: str, query: str, ctx: Context, limit: int = 10) -> Any:
    """Active controls whose title or statement contains the words given. framework is the id, exactly "800-171"."""
    return await _guarded_call(ctx, "search_controls", {"framework": framework, "query": query, "limit": limit})


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
