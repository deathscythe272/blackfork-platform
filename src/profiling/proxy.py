"""A logging proxy in front of the model endpoint. Every call's tokens and latency, on disk.

    python -m profiling.proxy            # listens on 0.0.0.0:8765, forwards to NVIDIA

Point any OpenAI-compatible client at http://localhost:8765/v1 (or
http://host.docker.internal:8765/v1 from a container). The proxy:

  - forwards /v1/chat/completions and /v1/models upstream with the key from NVIDIA_API_KEY
  - turns reasoning off (chat_template_kwargs.enable_thinking=false) unless the request
    sets it or sends X-Allow-Thinking: 1, so callers get the platform's calling convention
  - appends one JSON line per call to profiling/calls.jsonl: timestamp, model, prompt and
    completion tokens, latency, status, streaming flag, and an optional X-Profile-Tag
  - passes streamed responses through and reads usage from the final chunk

It stores no prompt or completion text. Serves: BR-9 (W1), and it is the reasoning-off
endpoint the Garak follow-up on the seeded-attacks page needs.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import threading
import time

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

UPSTREAM = os.environ.get("NIM_UPSTREAM", "https://integrate.api.nvidia.com/v1")
LOG = pathlib.Path(os.environ.get("PROFILE_LOG", "profiling/calls.jsonl"))
KEY = os.environ.get("NVIDIA_API_KEY", "")
app = FastAPI()
_lock = threading.Lock()
_client = httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=10.0))


def _log(row: dict) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with _lock, LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, separators=(",", ":")) + "\n")


@app.get("/v1/models")
async def models():
    r = await _client.get(f"{UPSTREAM}/models", headers={"Authorization": f"Bearer {KEY}"})
    return Response(content=r.content, status_code=r.status_code, media_type="application/json")


@app.post("/v1/chat/completions")
async def chat(request: Request):
    body = await request.json()
    if "chat_template_kwargs" not in body and request.headers.get("x-allow-thinking") != "1":
        body["chat_template_kwargs"] = {"enable_thinking": False}
    stream = bool(body.get("stream"))
    if stream:
        body.setdefault("stream_options", {})["include_usage"] = True
    row = {"ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds"),
           "tag": request.headers.get("x-profile-tag"), "model": body.get("model"), "stream": stream,
           "messages": len(body.get("messages") or []), "max_tokens": body.get("max_tokens")}
    headers = {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json", "Accept": request.headers.get("accept", "application/json")}
    started = time.perf_counter()

    if not stream:
        r = await _client.post(f"{UPSTREAM}/chat/completions", json=body, headers=headers)
        row["latency_ms"] = round((time.perf_counter() - started) * 1000, 1)
        row["status"] = r.status_code
        try:
            usage = r.json().get("usage") or {}
            row.update(prompt_tokens=usage.get("prompt_tokens"), completion_tokens=usage.get("completion_tokens"))
        except ValueError:
            pass
        _log(row)
        return Response(content=r.content, status_code=r.status_code, media_type=r.headers.get("content-type", "application/json"))

    async def gen():
        usage = {}
        async with _client.stream("POST", f"{UPSTREAM}/chat/completions", json=body, headers=headers) as r:
            row["status"] = r.status_code
            async for chunk in r.aiter_bytes():
                for line in chunk.decode("utf-8", "ignore").splitlines():
                    if line.startswith("data: ") and '"usage"' in line:
                        try:
                            u = json.loads(line[6:]).get("usage") or {}
                            if u:
                                usage = u
                        except json.JSONDecodeError:
                            pass
                yield chunk
        row["latency_ms"] = round((time.perf_counter() - started) * 1000, 1)
        row.update(prompt_tokens=usage.get("prompt_tokens"), completion_tokens=usage.get("completion_tokens"))
        _log(row)

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/healthz")
async def healthz():
    return JSONResponse({"ok": True, "upstream": UPSTREAM, "log": str(LOG)})


if __name__ == "__main__":
    import uvicorn

    if not KEY:
        raise SystemExit("NVIDIA_API_KEY is not set")
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PROFILE_PROXY_PORT", "8765")), log_level="warning")
