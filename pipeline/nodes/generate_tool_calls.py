"""
Node 3b: generate_tool_calls
Agent 시나리오(single_A / single_B / single_C)에 대해 선택된 모든 모델을
비동기 병렬 호출하여 Tool 호출 응답(JSON)을 수집한다.
설계 기준: docs/BenchMate_Agent설계.md — Node 3b
Multi-turn 시나리오는 현재 미구현 (스킵).
"""

import asyncio
import json
import os
import time
from typing import List, Optional

from dotenv import load_dotenv

from pipeline.nodes._async_utils import run_async
from pipeline.state import EvalState, ModelResponse, ScenarioItem, ToolDefinition

load_dotenv()

DOMAIN_NAMES: dict[str, str] = {
    "finance": "금융",
    "legal": "법무",
    "hr": "인사",
    "cs": "고객서비스",
    "manufacturing": "제조",
}

TOOL_SYSTEM_PROMPT = """\
당신은 기업 업무를 처리하는 AI Agent입니다.
사용자 요청을 분석하고, 아래 도구 중 적합한 것을 선택해 호출하세요.

사용 가능한 도구:
{tool_definitions}

반드시 아래 JSON 형식으로만 응답하세요. 다른 텍스트는 출력하지 마세요.
{{
  "tool_name": "<도구 이름>",
  "parameters": {{<파라미터 키-값>}}
}}

적합한 도구가 없거나 정보가 부족하면:
- 정보 부족: {{"action": "ask", "message": "<필요한 정보 요청>"}}
- 불가능한 요청: {{"action": "reject", "message": "<거절 이유>"}}\
"""


def _format_tool_definitions(tools: List[ToolDefinition]) -> str:
    """ToolDefinition 목록을 시스템 프롬프트 삽입용 텍스트로 변환."""
    lines: List[str] = []
    for tool in tools:
        param_descs = ", ".join(
            f"{p['name']} ({p['type']}, {'필수' if p.get('required') else '선택'}): {p['description']}"
            for p in tool["parameters"]
        )
        lines.append(f"- {tool['name']}: {tool['description']}\n  파라미터: {param_descs}")
    return "\n".join(lines)


def _try_parse_json(text: str) -> Optional[dict]:
    """JSON 파싱 시도. 실패 시 None 반환."""
    try:
        return json.loads(text.strip())
    except (json.JSONDecodeError, ValueError):
        # 코드 펜스 제거 후 재시도
        cleaned = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        try:
            return json.loads(cleaned)
        except (json.JSONDecodeError, ValueError):
            return None


def _resolve_model_name(model_name: str) -> str:
    """UI 모델 키 → 실제 API 모델명으로 변환."""
    _MODEL_MAP: dict[str, str] = {
        "solar-pro":     "solar-pro",
        "gpt-4o":        "gpt-4o",
        "claude-sonnet": "claude-sonnet-4-5",
    }
    return _MODEL_MAP.get(model_name, model_name)


def _client_type(model_name: str) -> str:
    name = model_name.lower()
    if "solar" in name or "upstage" in name:
        return "upstage"
    elif "gpt" in name or name.startswith("o1") or name.startswith("o3"):
        return "openai"
    elif "claude" in name:
        return "anthropic"
    raise ValueError(f"알 수 없는 모델 (upstage/openai/anthropic 분기 불가): {model_name}")


async def _call_upstage(model_name: str, system_prompt: str, user_message: str) -> dict:
    from openai import AsyncOpenAI

    client = AsyncOpenAI(
        api_key=os.environ["UPSTAGE_API_KEY"],
        base_url="https://api.upstage.ai/v1",
    )
    resp = await client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        temperature=0.0,
    )
    return {
        "text": resp.choices[0].message.content or "",
        "input_tokens": resp.usage.prompt_tokens,
        "output_tokens": resp.usage.completion_tokens,
    }


async def _call_openai(model_name: str, system_prompt: str, user_message: str) -> dict:
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])
    resp = await client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        temperature=0.0,
    )
    return {
        "text": resp.choices[0].message.content or "",
        "input_tokens": resp.usage.prompt_tokens,
        "output_tokens": resp.usage.completion_tokens,
    }


async def _call_anthropic(model_name: str, system_prompt: str, user_message: str) -> dict:
    import anthropic

    client = anthropic.AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    resp = await client.messages.create(
        model=model_name,
        max_tokens=512,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )
    text = resp.content[0].text if resp.content else ""
    return {
        "text": text,
        "input_tokens": resp.usage.input_tokens,
        "output_tokens": resp.usage.output_tokens,
    }


async def _call_with_retry(
    model_name: str,
    system_prompt: str,
    user_message: str,
    client_type: str,
    max_retries: int = 3,
    backoff: float = 2.0,
) -> dict:
    """최대 3회 지수 백오프 재시도 (2초 → 4초 → 8초)."""
    last_exc: Exception = RuntimeError("알 수 없는 오류")
    for attempt in range(max_retries):
        try:
            if client_type == "upstage":
                return await _call_upstage(model_name, system_prompt, user_message)
            elif client_type == "openai":
                return await _call_openai(model_name, system_prompt, user_message)
            else:
                return await _call_anthropic(model_name, system_prompt, user_message)
        except Exception as e:
            last_exc = e
            if attempt < max_retries - 1:
                await asyncio.sleep(backoff * (2 ** attempt))
    raise last_exc


def _build_system_prompt(scenario: ScenarioItem, all_tools: List[ToolDefinition]) -> str:
    """시나리오의 available_tools 필터링 후 시스템 프롬프트 생성."""
    scenario_tool_names = set(scenario["available_tools"])
    filtered_tools = [t for t in all_tools if t["name"] in scenario_tool_names]
    tool_text = _format_tool_definitions(filtered_tools)
    return TOOL_SYSTEM_PROMPT.format(tool_definitions=tool_text)


def _get_user_message(scenario: ScenarioItem) -> str:
    """Single-turn 시나리오에서 첫 번째 user 턴의 content를 추출."""
    for turn in scenario["turns"]:
        if turn["role"] == "user":
            return turn["content"]
    return ""


async def _call_model(
    model_name: str,
    scenario: ScenarioItem,
    all_tools: List[ToolDefinition],
) -> ModelResponse:
    api_model_name = _resolve_model_name(model_name)
    system_prompt = _build_system_prompt(scenario, all_tools)
    user_message = _get_user_message(scenario)
    ctype = _client_type(api_model_name)
    print(
        f"[generate_tool_calls] model_key={model_name!r} "
        f"→ api_model={api_model_name!r} / client={ctype} "
        f"/ scenario_id={scenario['id']!r}"
    )
    start = time.time()
    try:
        result = await _call_with_retry(api_model_name, system_prompt, user_message, ctype)
        raw_text = result["text"]
        parsed = _try_parse_json(raw_text)
        return ModelResponse(
            model_name=model_name,
            item_id=scenario["id"],
            response_text="",
            tool_call_output=parsed,
            raw_output=raw_text,
            latency_ms=int((time.time() - start) * 1000),
            input_tokens=result["input_tokens"],
            output_tokens=result["output_tokens"],
            status="success",
        )
    except Exception as e:
        return ModelResponse(
            model_name=model_name,
            item_id=scenario["id"],
            response_text="",
            tool_call_output=None,
            raw_output=str(e),
            latency_ms=int((time.time() - start) * 1000),
            input_tokens=0,
            output_tokens=0,
            status="failed",
        )


async def _gather_tool_calls(
    selected_models: List[str],
    scenarios: List[ScenarioItem],
    all_tools: List[ToolDefinition],
) -> List[ModelResponse]:
    single_scenarios = [s for s in scenarios if s["scenario_type"] in ("single_A", "single_B", "single_C")]
    tasks = [
        _call_model(model, scenario, all_tools)
        for model in selected_models
        for scenario in single_scenarios
    ]
    return list(await asyncio.gather(*tasks))


def generate_tool_calls(state: EvalState) -> dict:
    new_responses = run_async(
        _gather_tool_calls(
            state.get("selected_models", []),
            state.get("scenarios", []),
            state.get("available_tools", []),
        )
    )
    return {"model_responses": state.get("model_responses", []) + new_responses}
