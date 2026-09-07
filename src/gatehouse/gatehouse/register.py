"""The Gatehouse judge as a NeMo Agent Toolkit function.

Input: a JSON bundle (see gatehouse.judge.gather). Output: a JSON verdict with one
entry per rubric item and a list of findings. The judge has no tools. It cannot merge,
cannot post, and cannot change its rubric; those are done by separate code that reads
its output. The bundle is data; the rubric is the only instruction.

Serves: BR-3, BR-9 (and BR-8: the judge is itself an agent under the threat model).
"""

from __future__ import annotations

import asyncio
import json
import pathlib

from pydantic import Field

from nat.builder.builder import Builder
from nat.builder.framework_enum import LLMFrameworkEnum
from nat.builder.function_info import FunctionInfo
from nat.cli.register_workflow import register_function
from nat.data_models.component_ref import LLMRef
from nat.data_models.function import FunctionBaseConfig

from gatehouse.judge.prompt import build_messages, parse_verdict

DEFAULT_RUBRIC = pathlib.Path(__file__).resolve().parent / "judge" / "rubric.yml"


class GatehouseJudgeConfig(FunctionBaseConfig, name="gatehouse_judge"):
    """Score a pull-request bundle against the versioned rubric."""

    llm_name: LLMRef = Field(description="LLM used to score the bundle.")
    rubric_path: str = Field(default=str(DEFAULT_RUBRIC), description="Path to rubric.yml.")
    description: str = Field(default="Gatehouse judge: rubric scoring of a pull request bundle.")


@register_function(config_type=GatehouseJudgeConfig, framework_wrappers=[LLMFrameworkEnum.LANGCHAIN])
async def gatehouse_judge(config: GatehouseJudgeConfig, builder: Builder):
    llm = await builder.get_llm(config.llm_name, wrapper_type=LLMFrameworkEnum.LANGCHAIN)
    rubric_text = pathlib.Path(config.rubric_path).read_text(encoding="utf-8")

    async def _judge(bundle_json: str) -> str:
        bundle = json.loads(bundle_json)
        messages = build_messages(rubric_text, bundle)
        last_error: Exception | None = None
        for attempt in range(3):  # transport failures on the hosted tier are retried; verdicts are not
            try:
                response = await llm.ainvoke(messages)
                break
            except Exception as e:  # noqa: BLE001 - any transport error; the model output is never here
                last_error = e
                await asyncio.sleep(2 * (attempt + 1))
        else:
            raise RuntimeError(f"judge model call failed after 3 attempts: {last_error}")
        content = response.content if hasattr(response, "content") else str(response)
        verdict = parse_verdict(content, rubric_text, bundle.get("signals"))
        verdict["attempts"] = attempt + 1
        return json.dumps(verdict)

    yield FunctionInfo.from_fn(_judge, description=config.description)
