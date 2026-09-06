"""Run the Evidence Collector once, wrapped in Guardrails, and print a JSON result.

    python -m provenance.agent.run "For sys-windrow-prod, what evidence covers control 3.3.1?"

Order of operations, which is the point of the slice:

  1. input rail   - NeMo Guardrails scores the question; blocked questions never
                    reach the agent or the door
  2. agent        - NeMo Agent Toolkit ReAct workflow; its only tools are the ones the
                    gateway exposes; every tool call carries the service token
  3. output rail  - Guardrails scores the answer; blocked answers are replaced

Environment: NVIDIA_API_KEY, GATEWAY_URL, GATEWAY_TOKEN, OTEL_ENDPOINT.
Serves: BR-7, BR-8, BR-9.
"""

from __future__ import annotations

import asyncio
import json
import os
import pathlib
import sys
import tempfile
import time

HERE = pathlib.Path(__file__).resolve().parent
REFUSAL = "Request refused by the input guardrail."
OUTPUT_REFUSAL = "Answer withheld by the output guardrail."


def _render_config() -> pathlib.Path:
    template = (HERE / "config.template.yml").read_text(encoding="utf-8")
    values = {
        "__GATEWAY_URL__": os.environ.get("GATEWAY_URL", "http://localhost:8000/mcp"),
        "__GATEWAY_TOKEN__": os.environ["GATEWAY_TOKEN"],
        "__OTEL_ENDPOINT__": os.environ.get("OTEL_ENDPOINT", "http://localhost:4318/v1/traces"),
    }
    for k, v in values.items():
        template = template.replace(k, v)
    tmp = tempfile.NamedTemporaryFile("w", suffix=".yml", delete=False, encoding="utf-8")
    tmp.write(template)
    tmp.close()
    return pathlib.Path(tmp.name)


def _rail_blocked(result) -> bool:
    log = getattr(result, "log", None)
    for rail in (getattr(log, "activated_rails", None) or []):
        if getattr(rail, "stop", False):
            return True
    return False


async def _rails():
    from nemoguardrails import LLMRails, RailsConfig

    config = RailsConfig.from_path(str(HERE / "guardrails"))
    return LLMRails(config)


async def _check_input(rails, question: str) -> bool:
    res = await rails.generate_async(
        messages=[{"role": "user", "content": question}],
        options={"rails": ["input"], "log": {"activated_rails": True}},
    )
    return _rail_blocked(res)


async def _check_output(rails, question: str, answer: str) -> bool:
    res = await rails.generate_async(
        messages=[{"role": "user", "content": question}, {"role": "assistant", "content": answer}],
        options={"rails": ["output"], "log": {"activated_rails": True}},
    )
    return _rail_blocked(res)


async def _run_agent(question: str) -> str:
    from nat.runtime.loader import load_workflow

    config_path = _render_config()
    try:
        async with load_workflow(config_path) as workflow:
            async with workflow.run(question) as runner:
                return await runner.result(to_type=str)
    finally:
        config_path.unlink(missing_ok=True)


async def main(question: str) -> dict:
    started = time.perf_counter()
    out = {"question": question, "input_blocked": False, "output_blocked": False, "answer": None, "error": None}
    rails = await _rails()

    if await _check_input(rails, question):
        out["input_blocked"] = True
        out["answer"] = REFUSAL
    else:
        try:
            answer = await _run_agent(question)
        except Exception as e:  # the agent failing is a result, not a crash of the harness
            out["error"] = f"{e.__class__.__name__}: {e}"
            answer = f"The agent could not complete the request: {e.__class__.__name__}"
        if await _check_output(rails, question, answer):
            out["output_blocked"] = True
            out["answer"] = OUTPUT_REFUSAL
        else:
            out["answer"] = answer

    out["latency_s"] = round(time.perf_counter() - started, 2)
    return out


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    result = asyncio.run(main(" ".join(sys.argv[1:])))
    print("\n=== RESULT ===")
    print(json.dumps(result, indent=2))
