"""
Node 3a: generate_responses
Knowledge 문항 목록에 대해 선택된 모든 모델을 비동기 병렬 호출하여 응답을 수집한다.
설계 기준: docs/BenchMate_Agent설계.md — Node 3a
"""

import asyncio
import os
import time
from typing import List

from dotenv import load_dotenv

from pipeline.state import EvalState, ModelResponse, QuestionItem

load_dotenv()

DOMAIN_NAMES: dict[str, str] = {
    "finance": "금융",
    "legal": "법무",
    "hr": "인사",
    "cs": "고객서비스",
    "manufacturing": "제조",
}


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
        temperature=0.3,
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
        temperature=0.3,
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
        max_tokens=1024,
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


async def _call_model(model_name: str, question: QuestionItem) -> ModelResponse:
    domain_kr = DOMAIN_NAMES.get(question["domain"], question["domain"])
    system_prompt = (
        f"당신은 {domain_kr} 도메인 전문가입니다. "
        "질문에 정확하고 자연스러운 한국어로 답변하세요."
    )
    ctype = _client_type(model_name)
    start = time.time()
    try:
        result = await _call_with_retry(model_name, system_prompt, question["question"], ctype)
        return ModelResponse(
            model_name=model_name,
            item_id=question["id"],
            response_text=result["text"],
            tool_call_output=None,
            raw_output=None,
            latency_ms=int((time.time() - start) * 1000),
            input_tokens=result["input_tokens"],
            output_tokens=result["output_tokens"],
            status="success",
        )
    except Exception as e:
        return ModelResponse(
            model_name=model_name,
            item_id=question["id"],
            response_text="",
            tool_call_output=None,
            raw_output=str(e),
            latency_ms=int((time.time() - start) * 1000),
            input_tokens=0,
            output_tokens=0,
            status="failed",
        )


async def _gather_responses(
    selected_models: List[str],
    questions: List[QuestionItem],
) -> List[ModelResponse]:
    tasks = [
        _call_model(model, question)
        for model in selected_models
        for question in questions
    ]
    return list(await asyncio.gather(*tasks))


def generate_responses(state: EvalState) -> dict:
    responses = asyncio.run(
        _gather_responses(state["selected_models"], state["questions"])
    )
    return {"model_responses": responses}
