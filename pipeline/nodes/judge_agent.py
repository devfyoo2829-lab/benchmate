"""
Node 4c: judge_agent
시나리오 유형에 따라 slot / relevance / completion 항목을 Qwen 2.5-32B Judge로 채점한다.
call_score는 evaluate_call 노드가 이미 채운 값을 유지하고, 나머지 항목만 업데이트한다.
설계 기준: docs/BenchMate_Agent설계.md — Node 4c
"""

import asyncio
import json
import os
import re
from pathlib import Path
from typing import Dict, List, Optional

from dotenv import load_dotenv
from jinja2 import Environment, FileSystemLoader

from pipeline.state import AgentScore, EvalState, ModelResponse, ScenarioItem

load_dotenv()

_PROMPTS_DIR = Path(__file__).parent.parent.parent / "prompts"
_jinja_env = Environment(loader=FileSystemLoader(str(_PROMPTS_DIR)))


def _get_eval_type(scenario: ScenarioItem, turn_index: int) -> Optional[str]:
    """시나리오 유형과 턴 인덱스에 따라 채점 항목 결정."""
    stype = scenario["scenario_type"]
    if stype == "single_B":
        return "slot"
    elif stype == "single_C":
        return "relevance"
    elif stype == "single_A":
        return "completion"
    elif stype == "multi":
        turns = scenario["turns"]
        if turn_index < len(turns):
            expects = turns[turn_index].get("expects")
            if expects == "slot":
                return "slot"
            elif expects == "rejection":
                return "relevance"
            elif expects == "completion":
                return "completion"
    return None


def _get_user_input(scenario: ScenarioItem) -> str:
    """첫 번째 user 턴의 content 반환."""
    for turn in scenario["turns"]:
        if turn["role"] == "user":
            return turn["content"]
    return ""


def _get_tool_result(scenario: ScenarioItem) -> str:
    """tool_result 턴의 content 반환 (completion 채점에 사용)."""
    for turn in scenario["turns"]:
        if turn["role"] == "tool_result":
            content = turn.get("content", "")
            return json.dumps(content, ensure_ascii=False) if isinstance(content, dict) else str(content)
    return ""


def _build_prompt(eval_type: str, user_input: str, model_response: str, tool_result: str) -> str:
    template = _jinja_env.get_template("agent_judge_template.txt")
    return template.render(
        eval_type=eval_type,
        user_input=user_input,
        model_response=model_response,
        tool_result=tool_result,
    )


def _parse_judge_output(raw: str) -> dict:
    """Judge 원본 응답에서 JSON 파싱. 실패 시 예외 발생."""
    cleaned = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        return json.loads(match.group())
    return json.loads(cleaned)


async def _call_qwen(prompt: str) -> str:
    """HuggingFace Inference API로 Qwen 2.5-32B-Instruct 호출."""
    from huggingface_hub import AsyncInferenceClient

    client = AsyncInferenceClient(
        model="Qwen/Qwen2.5-32B-Instruct",
        token=os.environ["HF_TOKEN"],
    )
    response = await client.chat_completion(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
        max_tokens=256,
    )
    return response.choices[0].message.content or ""


async def _judge_single(
    score: AgentScore,
    scenario: ScenarioItem,
    response: ModelResponse,
) -> AgentScore:
    """단일 AgentScore에 대해 Judge 호출 후 slot/relevance/completion 업데이트."""
    eval_type = _get_eval_type(scenario, score["turn_index"])
    if eval_type is None:
        return score

    user_input = _get_user_input(scenario)
    model_response = response.get("raw_output") or response.get("response_text") or ""
    tool_result = _get_tool_result(scenario) if eval_type == "completion" else ""

    prompt = _build_prompt(eval_type, user_input, model_response, tool_result)
    raw = await _call_qwen(prompt)

    updated: dict = dict(score)
    try:
        parsed = _parse_judge_output(raw)
        judge_score = int(parsed["score"])
        reason = str(parsed.get("reason", ""))

        if eval_type == "slot":
            updated["slot_score"] = judge_score
        elif eval_type == "relevance":
            updated["relevance_score"] = judge_score
        elif eval_type == "completion":
            updated["completion_score"] = judge_score

        updated["reason"] = reason
    except Exception:
        updated["_parse_failed"] = True
        updated["_raw_output"] = raw

    return updated  # type: ignore[return-value]


async def _noop(score: AgentScore) -> AgentScore:
    return score


async def _judge_all(
    agent_scores: List[AgentScore],
    scenarios: List[ScenarioItem],
    model_responses: List[ModelResponse],
) -> List[AgentScore]:
    """모든 AgentScore에 대해 비동기 병렬 Judge 호출."""
    scenario_map: Dict[str, ScenarioItem] = {s["id"]: s for s in scenarios}
    response_map: Dict[tuple, ModelResponse] = {
        (r["item_id"], r["model_name"]): r for r in model_responses
    }

    tasks = []
    for score in agent_scores:
        scenario = scenario_map.get(score["scenario_id"])
        response = response_map.get((score["scenario_id"], score["model_name"]))
        if scenario is None or response is None:
            tasks.append(_noop(score))
        else:
            tasks.append(_judge_single(score, scenario, response))

    return list(await asyncio.gather(*tasks))


def judge_agent(state: EvalState) -> dict:
    updated_scores = asyncio.run(
        _judge_all(
            state["agent_scores"],
            state["scenarios"],
            state["model_responses"],
        )
    )
    return {"agent_scores": updated_scores}
