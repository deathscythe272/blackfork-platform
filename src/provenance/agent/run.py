"""Run one agent job, wrapped in Guardrails, and return a JSON-able result.

    python -m provenance.agent.run "For sys-windrow-prod, what evidence covers control 3.3.1?"

Order of operations, which is the point of the slice:

  1. input rail   - NeMo Guardrails scores the question; blocked questions never
                    reach the agent or the door
  2. agent        - NeMo Agent Toolkit ReAct workflow; its only tools are the ones the
                    gateway exposes; every tool call carries the agent's token
  3. output rail  - Guardrails scores the answer; blocked answers are replaced

Each agent is a configuration template (config.template.yml for the Evidence
Collector, config-mapper.template.yml for the Control Mapper) rendered at start with
the gateway address and the agent's token, so no token or endpoint is ever written
into the repo. The token comes from the environment for a one-shot run, or from the
agent service, which mints one per job for the agent's own identity.

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
AGENTS = {
    "evidence-collector": "config.template.yml",
    "control-mapper": "config-mapper.template.yml",
}


def _render_config(template_name: str, token: str | None) -> pathlib.Path:
    template = (HERE / template_name).read_text(encoding="utf-8")
    values = {
        "__GATEWAY_URL__": os.environ.get("GATEWAY_URL", "http://localhost:8000/mcp"),
        "__GATEWAY_TOKEN__": token or os.environ["GATEWAY_TOKEN"],
        "__OTEL_ENDPOINT__": os.environ.get("OTEL_ENDPOINT", "http://localhost:4318/v1/traces"),
        "__NIM_BASE_URL__": os.environ.get("NIM_BASE_URL", "https://integrate.api.nvidia.com/v1"),
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


async def _run_agent(question: str, template_name: str, token: str | None) -> str:
    from nat.runtime.loader import load_workflow

    config_path = _render_config(template_name, token)
    try:
        async with load_workflow(config_path) as workflow:
            async with workflow.run(question) as runner:
                return await runner.result(to_type=str)
    finally:
        config_path.unlink(missing_ok=True)


async def main(question: str, agent: str = "evidence-collector", token: str | None = None) -> dict:
    if agent not in AGENTS:
        raise ValueError(f"unknown agent {agent!r}; known: {sorted(AGENTS)}")
    started = time.perf_counter()
    out = {"agent": agent, "question": question, "input_blocked": False, "output_blocked": False, "answer": None, "error": None}
    rails = await _rails()

    if await _check_input(rails, question):
        out["input_blocked"] = True
        out["answer"] = REFUSAL
    else:
        try:
            answer = await _run_agent(question, AGENTS[agent], token)
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
