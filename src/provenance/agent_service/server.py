"""The agent service: agents as a service behind a signed-token door, with a quota per
caller and a record per job.

  POST /jobs   {"agent": "evidence-collector" | "control-mapper" | "assessor" | "report-writer", "input": {...}}
  GET  /packets/{id}          the draft or signed packet, JSON
  POST /packets/{id}/sign     a person's signature; the caller token's role must be
                              `person`, which no agent token carries (ADR-007)
  GET  /packets/{id}/export   the packet as markdown, refused (409) unless signed and
                              unchanged since the signature
               header X-Caller-Token: a token for the caller's identity, signed with the
               same key the gateway trusts. The service verifies it, applies the
               caller's quota (T1-IN-04), mints a short-lived token for the agent's own
               identity, runs the job with its rails, and records it.
  GET  /health   (not /healthz: the cloud's front door reserves that path and answers it itself)

Inputs: the Evidence Collector takes {"question": ...}; the Control Mapper and the
assessor take {"system_id": ..., "control_id": ...}; the Report Writer takes
{"system_id": ..., "control_ids": [...]} (control_ids optional: all of the system's). The assessor is the investigation
workflow: the mapper's statement plus the Risk Analyst's verdict, reached over A2A. The caller's identity and the agent's identity
are different tokens on purpose: a caller may ask for a job, but only the agent's
identity is granted tools at the door, and only for the length of one job.

Environment: GATEWAY_SIGNING_KEY, GATEWAY_URL, NVIDIA_API_KEY, OTEL_ENDPOINT,
AGENT_JOB_QUOTA (jobs per caller per window, default 30), AGENT_JOB_WINDOW_SECONDS
(default 3600), AGENT_JOBS_LOG (default jobs/jobs.jsonl). Serves: BR-3, BR-7, BR-8.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import pathlib
import time
import uuid
from typing import Any, Awaitable, Callable

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Route

from provenance.gateway.ratelimit import Limiter
from provenance.gateway.tokens import IdentityError, claims, mint
from provenance.packets import store

AGENTS = ("evidence-collector", "control-mapper", "assessor", "report-writer")
JOB_TOKEN_TTL_S = 900

Runner = Callable[[str, dict[str, Any], str], Awaitable[dict[str, Any]]]


async def default_runner(agent: str, job_input: dict[str, Any], token: str) -> dict[str, Any]:
    """Run the named agent in this process with its rails; the real thing."""
    if agent == "control-mapper":
        from provenance.agent.mapper import main as mapper_main

        return await mapper_main(str(job_input["system_id"]), str(job_input["control_id"]), token=token)
    if agent == "assessor":
        from provenance.agent.assess import main as assess_main

        return await assess_main(str(job_input["system_id"]), str(job_input["control_id"]), token=token)
    if agent == "report-writer":
        from provenance.agent.writer import main as writer_main

        ids = [str(c) for c in (job_input.get("control_ids") or [])] or None
        return await writer_main(str(job_input["system_id"]), ids, token=token)
    from provenance.agent.run import main as run_main

    return await run_main(str(job_input["question"]), agent=agent, token=token)


def validate_input(agent: str, job_input: Any) -> str | None:
    if agent not in AGENTS:
        return f"unknown agent; known: {list(AGENTS)}"
    if not isinstance(job_input, dict):
        return "input must be an object"
    need = {"control-mapper": ("system_id", "control_id"), "assessor": ("system_id", "control_id"),
            "report-writer": ("system_id",)}.get(agent, ("question",))
    missing = [k for k in need if not str(job_input.get(k, "")).strip()]
    return f"input needs {', '.join(need)}" if missing else None


class JobLog:
    def __init__(self, path: pathlib.Path):
        self.path = path

    def write(self, record: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n")


def build_app(runner: Runner = default_runner, env: dict[str, str] | None = None) -> Starlette:
    env = os.environ if env is None else env
    quota = Limiter(int(env.get("AGENT_JOB_QUOTA", "30")), float(env.get("AGENT_JOB_WINDOW_SECONDS", "3600")))
    log = JobLog(pathlib.Path(env.get("AGENT_JOBS_LOG", "jobs/jobs.jsonl")))

    async def healthz(_: Request) -> JSONResponse:
        return JSONResponse({"ok": True, "agents": list(AGENTS)})

    async def jobs(request: Request) -> JSONResponse:
        started = time.perf_counter()
        job_id = str(uuid.uuid4())
        record: dict[str, Any] = {"id": job_id, "ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds")}
        token = request.headers.get("x-caller-token", "").strip()
        try:
            caller = claims(token)["sub"] if token else None
        except IdentityError as e:
            caller = None
            record["identity_error"] = str(e)
        if not caller:
            record.update(caller=None, status="refused: no valid caller token")
            log.write(record)
            return JSONResponse({"error": "a valid X-Caller-Token is required"}, status_code=401)
        record["caller"] = caller

        try:
            body = await request.json()
        except ValueError:
            body = {}
        agent, job_input = body.get("agent", ""), body.get("input")
        problem = validate_input(agent, job_input)
        if problem:
            record.update(agent=agent, status=f"refused: {problem}")
            log.write(record)
            return JSONResponse({"error": problem}, status_code=400)
        record["agent"] = agent
        record["input_sha256"] = hashlib.sha256(json.dumps(job_input, sort_keys=True).encode()).hexdigest()[:16]

        verdict = quota.check(caller)
        if not verdict.allowed:
            record.update(status="refused: quota", retry_after_s=verdict.retry_after_s)
            log.write(record)
            return JSONResponse({"error": f"quota: over {quota.limit} jobs per {quota.window_s:.0f}s for this caller",
                                 "retry_after_s": verdict.retry_after_s}, status_code=429)

        # the agent's own identity, for this job only; the assessor and the writer work as the mapper at the door
        agent_token = mint("control-mapper" if agent in ("assessor", "report-writer") else agent, ttl_seconds=JOB_TOKEN_TTL_S, role="agent")
        try:
            result = await runner(agent, job_input, agent_token)
            status = "ok" if not result.get("error") else "agent error"
        except Exception as e:  # the runner failing is a result, not a crash of the service
            result = {"error": f"{e.__class__.__name__}: {e}", "answer": None}
            status = "runner error"
        record.update(status=status, duration_ms=round((time.perf_counter() - started) * 1000, 1),
                      input_blocked=bool(result.get("input_blocked")), output_blocked=bool(result.get("output_blocked")),
                      answer_chars=len(result.get("answer") or ""))
        log.write(record)
        return JSONResponse({"job_id": job_id, "agent": agent, "caller": caller, "status": status, **result})

    def _caller(request: Request) -> dict[str, Any] | None:
        token = request.headers.get("x-caller-token", "").strip()
        if not token:
            return None
        try:
            return claims(token)
        except IdentityError:
            return None

    async def get_packet(request: Request) -> JSONResponse:
        if not _caller(request):
            return JSONResponse({"error": "a valid X-Caller-Token is required"}, status_code=401)
        packet = store.load(request.path_params["packet_id"])
        return JSONResponse(packet) if packet else JSONResponse({"error": "no such packet"}, status_code=404)

    async def sign_packet(request: Request) -> JSONResponse:
        who = _caller(request)
        if not who:
            return JSONResponse({"error": "a valid X-Caller-Token is required"}, status_code=401)
        record = {"id": str(uuid.uuid4()), "ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds"),
                  "caller": who["sub"], "role": who.get("role"), "packet_id": request.path_params["packet_id"], "action": "sign"}
        if who.get("role") != "person":
            record["status"] = "refused: only a person may sign"
            log.write(record)
            return JSONResponse({"error": "only a person may sign a packet; this token's role is " + str(who.get("role"))}, status_code=403)
        try:
            packet = store.sign(request.path_params["packet_id"], who["sub"], who["role"])
        except FileNotFoundError:
            record["status"] = "refused: no such packet"
            log.write(record)
            return JSONResponse({"error": "no such packet"}, status_code=404)
        record["status"] = "signed"
        log.write(record)
        return JSONResponse({"packet_id": packet["packet_id"], "status": packet["status"], "signature": packet["signature"]})

    async def export_packet(request: Request):
        if not _caller(request):
            return JSONResponse({"error": "a valid X-Caller-Token is required"}, status_code=401)
        try:
            packet, markdown = store.export(request.path_params["packet_id"])
        except FileNotFoundError:
            return JSONResponse({"error": "no such packet"}, status_code=404)
        except PermissionError as e:
            return JSONResponse({"error": str(e)}, status_code=409)
        return PlainTextResponse(markdown, media_type="text/markdown")

    return Starlette(routes=[
        Route("/health", healthz), Route("/jobs", jobs, methods=["POST"]),
        Route("/packets/{packet_id}", get_packet),
        Route("/packets/{packet_id}/sign", sign_packet, methods=["POST"]),
        Route("/packets/{packet_id}/export", export_packet),
    ])


app = build_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=os.environ.get("AGENT_SERVICE_HOST", "0.0.0.0"), port=int(os.environ.get("AGENT_SERVICE_PORT", "8080")))
