"""
BenchMate — Node 8: generate_report

summary_table을 기반으로 PM 해석 리포트(마크다운)를 자동 생성하고,
세션 전체 결과를 /output/{eval_session_id}.json으로 저장한다.

설계 기준: docs/BenchMate_Agent설계.md — Node 8
"""

import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

from dotenv import load_dotenv

from pipeline.state import EvalState

load_dotenv()

# 프로젝트 루트: pipeline/nodes/ → ../../
_PROJECT_ROOT = Path(__file__).parent.parent.parent
_OUTPUT_DIR = _PROJECT_ROOT / "output"

DOMAIN_NAMES: dict[str, str] = {
    "finance": "금융",
    "legal": "법무",
    "hr": "인사",
    "cs": "고객서비스",
    "manufacturing": "제조",
}

_REPORT_SYSTEM_PROMPT = (
    "당신은 기업 LLM 도입을 돕는 PM 전문가입니다. "
    "평가 결과를 비기술적 언어로 해석하여 실무 담당자가 바로 의사결정에 활용할 수 있는 리포트를 작성하세요. "
    "마크다운 형식으로 작성하며, 수치 근거를 명시하세요."
)

_REPORT_USER_TEMPLATE = """\
다음 LLM 평가 결과를 바탕으로 기업 실무 담당자를 위한 PM 해석 리포트를 작성하세요.

평가 요약:
- 평가 모드: {eval_mode}
- 도메인: {domain}
- 평가 모델: {models}
- Judge 신뢰도: {judge_reliability}

점수 테이블:
{summary_table_str}

비용 정보:
{cost_str}

리포트 구성 (아래 순서대로 마크다운 헤더를 사용하세요):
1. 평가 요약 (1~2문장)
2. 종합 추천 모델 및 핵심 근거
3. Knowledge vs Agent 괴리 분석
   - 지식 점수는 높지만 Tool calling이 약한 모델 식별
   - "A 모델은 ~~에 적합하고 ~~에는 부적합합니다" 형식
4. 도메인별 강점 모델
5. 고위험 항목 경고 (hallucination 낮음 / call 실패율 높음)
6. 비용 대비 성능 분석
7. 도입 우선순위 제안 3가지
"""


def _fmt(value: Optional[float]) -> str:
    if value is None:
        return "N/A"
    return f"{value:.2f}"


def _format_summary_table(summary_table: Optional[Dict]) -> str:
    """summary_table을 프롬프트에 삽입할 텍스트로 변환."""
    if not summary_table:
        return "(집계 데이터 없음)"

    lines: List[str] = []
    for model, sections in summary_table.items():
        lines.append(f"[{model}]")

        k = sections.get("knowledge", {})
        if k.get("question_count", 0) > 0:
            lines.append(
                f"  Knowledge (문항 {k['question_count']}개): "
                f"total={_fmt(k.get('total'))}, "
                f"accuracy={_fmt(k.get('accuracy'))}, "
                f"fluency={_fmt(k.get('fluency'))}, "
                f"hallucination={_fmt(k.get('hallucination'))}, "
                f"domain_expertise={_fmt(k.get('domain_expertise'))}, "
                f"utility={_fmt(k.get('utility'))}"
            )

        a = sections.get("agent", {})
        if a.get("scenario_count", 0) > 0:
            lines.append(
                f"  Agent (시나리오 {a['scenario_count']}개): "
                f"call={_fmt(a.get('call_score'))}, "
                f"slot={_fmt(a.get('slot_score'))}, "
                f"relevance={_fmt(a.get('relevance_score'))}, "
                f"completion={_fmt(a.get('completion_score'))}"
            )

    return "\n".join(lines) if lines else "(집계 데이터 없음)"


def _format_cost(estimated_cost: Optional[Dict]) -> str:
    if not estimated_cost:
        return "(비용 데이터 없음)"
    lines = []
    for k, v in estimated_cost.items():
        if k == "_total":
            lines.append(f"  합계: ${v:.6f}")
        else:
            lines.append(f"  {k}: ${v:.6f}")
    return "\n".join(lines)


def _build_report_prompt(state: EvalState) -> str:
    domain_kr = DOMAIN_NAMES.get(state.get("domain", ""), state.get("domain", ""))
    eval_mode = state.get("eval_mode", "")
    models = ", ".join(state.get("selected_models", []))
    judge_reliability = state.get("judge_reliability")
    reliability_str = f"{judge_reliability:.1f}%" if judge_reliability is not None else "미측정"

    return _REPORT_USER_TEMPLATE.format(
        eval_mode=eval_mode,
        domain=domain_kr,
        models=models,
        judge_reliability=reliability_str,
        summary_table_str=_format_summary_table(state.get("summary_table")),
        cost_str=_format_cost(state.get("estimated_cost")),
    )


async def _call_openai_report(prompt: str) -> str:
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])
    resp = await client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": _REPORT_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        max_tokens=2048,
    )
    return resp.choices[0].message.content or ""


async def _call_qwen_report(prompt: str) -> str:
    from huggingface_hub import AsyncInferenceClient

    client = AsyncInferenceClient(
        model="Qwen/Qwen2.5-32B-Instruct",
        token=os.environ["HF_TOKEN"],
    )
    full_prompt = f"{_REPORT_SYSTEM_PROMPT}\n\n{prompt}"
    response = await client.chat_completion(
        messages=[{"role": "user", "content": full_prompt}],
        temperature=0.3,
        max_tokens=2048,
    )
    return response.choices[0].message.content or ""


async def _generate_report_text(prompt: str) -> str:
    """GPT-4o 우선 시도, 실패 시 Qwen 2.5-32B 폴백."""
    if os.environ.get("OPENAI_API_KEY"):
        try:
            return await _call_openai_report(prompt)
        except Exception:
            pass

    return await _call_qwen_report(prompt)


def _save_session_json(state: EvalState, report_text: str) -> None:
    """세션 결과를 output/{eval_session_id}.json으로 저장."""
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    session_data = {
        "session_id": state.get("eval_session_id", ""),
        "eval_mode": state.get("eval_mode", ""),
        "domain": state.get("domain", ""),
        "selected_models": state.get("selected_models", []),
        "summary_table": state.get("summary_table"),
        "pm_report_text": report_text,
        "judge_reliability": state.get("judge_reliability"),
        "estimated_cost": state.get("estimated_cost"),
        "human_review_queue_count": len(state.get("human_review_queue", [])),
        "created_at": datetime.now(timezone(timedelta(hours=9))).isoformat(),
    }

    session_id = state.get("eval_session_id", "unknown")
    output_path = _OUTPUT_DIR / f"{session_id}.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(session_data, f, ensure_ascii=False, indent=2)


def generate_report(state: EvalState) -> dict:
    """
    PM 해석 리포트 생성 및 세션 JSON 저장 노드.

    입력:
        summary_table      — 모델별 Knowledge/Agent 집계
        judge_reliability  — Judge-Human 일치율 (%)
        estimated_cost     — 모델별 추정 비용 (USD)
        eval_session_id    — 세션 고유 ID
        eval_mode          — 평가 모드
        domain             — 평가 도메인
        selected_models    — 선택된 모델 목록

    출력:
        pm_report_text — PM 해석 리포트 마크다운 문자열
    """
    prompt = _build_report_prompt(state)
    report_text = asyncio.run(_generate_report_text(prompt))
    _save_session_json(state, report_text)
    return {"pm_report_text": report_text}
