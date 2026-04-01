"""
BenchMate — Node 8: generate_report

summary_table을 기반으로 PM 해석 리포트(마크다운)를 자동 생성하고,
세션 전체 결과를 /output/{eval_session_id}.json으로 저장한다.

설계 기준: docs/BenchMate_Agent설계.md — Node 8
"""

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

from dotenv import load_dotenv

from pipeline.nodes._async_utils import run_async
from pipeline.nodes._hf_error import translate_hf_error
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
    "아래 지시에 따라 지정된 마크다운 형식을 정확히 지켜 리포트를 작성하세요. "
    "비기술적 언어를 사용하고 수치 근거를 명시하세요. "
    "지정된 섹션 구조를 절대 변경하거나 생략하지 마세요."
)

_REPORT_USER_TEMPLATE = """\
아래 [평가 데이터]를 참고하여 [출력 템플릿]을 채워 최종 리포트를 출력하세요.
[출력 템플릿] 이외의 서두·설명·주석을 추가하지 마세요.
각 섹션에 표시된 지시문(※로 시작하는 줄)은 실제 출력에서 삭제하세요.

==========
[평가 데이터]

문서번호: {session_id}
평가일: {date}
평가 모드: {eval_mode}
도메인: {domain}
평가 모델: {models}
Judge 신뢰도: {judge_reliability}

[모델별 점수]
{summary_table_str}

[비용]
{cost_str}
==========

[출력 템플릿]

# BenchMate 평가 리포트
**문서번호**: {session_id}　　**평가일**: {date}

---

## 평가 개요

| 항목 | 내용 |
|---|---|
| 평가 도메인 | {domain} |
| 평가 모델 | {models} |
| 평가 모드 | {eval_mode} |
| Judge 신뢰도 | {judge_reliability} |

---

## 종합 추천 모델

> ### ※ [모델별 점수]에서 Knowledge 지식 총점이 가장 높은 모델명을 여기에 작성
>
> ※ 해당 모델을 추천하는 핵심 근거를 2~3문장으로 작성 (수치 포함)

---

## 모델별 점수 요약

※ [모델별 점수]의 Knowledge 점수표 데이터로 아래 표를 완성하세요.
※ 지식 총점은 5개 항목 합산(/25), 각 세부 항목은 /5 만점입니다.

| 모델 | 지식 총점(/25) | 사실 정확도(/5) | 허위정보 없음(/5) | 도메인 전문성(/5) |
|---|---|---|---|---|
※ 모델별로 한 행씩 채우세요

※ Agent 점수표가 있는 경우 아래 표도 추가하세요:

| 모델 | Tool 호출 정확도(/1) | 슬롯 채우기(/5) | 거절 적절성(/5) | 응답 완성도(/5) |
|---|---|---|---|---|
※ 모델별로 한 행씩 채우세요 (Agent 데이터가 없으면 이 표 전체 삭제)

---

## 강점 분석

※ 아래 2~3개 불릿으로 강점을 작성하세요. 수치 근거 필수 포함.

- **[강점명]**: ※ 가장 두드러진 강점 (예: 사실 정확도 1위, 점수 차이 등)
- **[강점명]**: ※ 두 번째 강점
- **[강점명]**: ※ (선택) 세 번째 강점

---

## 리스크 & 권고

※ 아래 2~3개 불릿으로 리스크 및 권고사항을 작성하세요. 수치 근거 포함.

- **도입 1순위**: ※ 추천 모델과 적합한 업무 유형
- **주의 사항**: ※ hallucination/call 실패 등 리스크 수치 명시
- **추가 검증 필요**: ※ 이번 평가에서 확인하지 못한 리스크 또는 추가 검증 항목

※ hallucination 점수가 2점 이하이거나 call_score 실패율이 50% 이상인 모델이 있으면
  아래 경고 블록을 추가하세요 (없으면 삭제):

> ⚠️ **고위험 경고**: ※ 해당 모델명과 위험 사유

---

## 비용 분석

※ [비용] 데이터로 아래 표를 완성하세요. 성능 대비 평가는 지식 총점 대비 비용 효율로 판단합니다.

| 모델 | 추정 비용(USD) | 성능 대비 평가 |
|---|---|---|
※ 모델별로 한 행씩 채우세요

---

*본 리포트는 AI가 자동 생성했습니다. 최종 결정은 담당자가 내려주세요.*
*BenchMate · {date}*
"""


def _fmt(value: Optional[float]) -> str:
    if value is None:
        return "N/A"
    return f"{value:.2f}"


def _format_summary_table(summary_table: Optional[Dict]) -> str:
    """summary_table을 마크다운 표로 변환하여 프롬프트에 삽입."""
    if not summary_table:
        return "(집계 데이터 없음)"

    # Knowledge 표
    k_header = "| 모델 | 지식 총점(/25) | 사실 정확도(/5) | 한국어 자연성(/5) | 허위정보 없음(/5) | 도메인 전문성(/5) | 응답 적절성(/5) |"
    k_sep    = "|---|---|---|---|---|---|---|"
    k_rows: List[str] = []

    # Agent 표
    a_header = "| 모델 | call(/1) | slot(/5) | relevance(/5) | completion(/5) |"
    a_sep    = "|---|---|---|---|---|"
    a_rows: List[str] = []

    for model, sections in summary_table.items():
        k = sections.get("knowledge", {})
        if k.get("question_count", 0) > 0:
            total_raw = k.get("total")
            total_25 = _fmt(total_raw)
            k_rows.append(
                f"| {model} | {total_25} "
                f"| {_fmt(k.get('accuracy'))} "
                f"| {_fmt(k.get('fluency'))} "
                f"| {_fmt(k.get('hallucination'))} "
                f"| {_fmt(k.get('domain_expertise'))} "
                f"| {_fmt(k.get('utility'))} |"
            )

        a = sections.get("agent", {})
        if a.get("scenario_count", 0) > 0:
            a_rows.append(
                f"| {model} "
                f"| {_fmt(a.get('call_score'))} "
                f"| {_fmt(a.get('slot_score'))} "
                f"| {_fmt(a.get('relevance_score'))} "
                f"| {_fmt(a.get('completion_score'))} |"
            )

    parts: List[str] = []
    if k_rows:
        parts.append("Knowledge 점수표:")
        parts += [k_header, k_sep] + k_rows
    if a_rows:
        if parts:
            parts.append("")
        parts.append("Agent 점수표:")
        parts += [a_header, a_sep] + a_rows

    return "\n".join(parts) if parts else "(집계 데이터 없음)"


def _format_cost(estimated_cost: Optional[Dict]) -> str:
    """estimated_cost를 마크다운 표로 변환하여 프롬프트에 삽입."""
    if not estimated_cost:
        return "(비용 데이터 없음)"

    header = "| 모델 | 추정 비용(USD) |"
    sep    = "|---|---|"
    rows: List[str] = []
    total_line = ""

    for k, v in estimated_cost.items():
        if k == "_total":
            total_line = f"| **합계** | **${v:.6f}** |"
        else:
            rows.append(f"| {k} | ${v:.6f} |")

    lines = [header, sep] + rows
    if total_line:
        lines.append(total_line)
    return "\n".join(lines)


def _build_report_prompt(state: EvalState) -> str:
    domain_kr = DOMAIN_NAMES.get(state.get("domain", ""), state.get("domain", ""))
    eval_mode = state.get("eval_mode", "")
    models = ", ".join(state.get("selected_models", []))
    judge_reliability = state.get("judge_reliability")
    reliability_str = f"{judge_reliability:.1f}%" if judge_reliability is not None else "미측정"
    session_id = state.get("eval_session_id", "")
    date = datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d")

    return _REPORT_USER_TEMPLATE.format(
        eval_mode=eval_mode,
        domain=domain_kr,
        models=models,
        judge_reliability=reliability_str,
        session_id=session_id,
        date=date,
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
        model="Qwen/Qwen2.5-7B-Instruct",
        token=os.environ["HF_TOKEN"],
    )
    full_prompt = f"{_REPORT_SYSTEM_PROMPT}\n\n{prompt}"
    try:
        response = await client.chat_completion(
            messages=[{"role": "user", "content": full_prompt}],
            temperature=0.3,
            max_tokens=2048,
        )
        return response.choices[0].message.content or ""
    except Exception as e:
        mapped = translate_hf_error(e)
        raise (mapped or e) from e


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
    report_text = run_async(_generate_report_text(prompt))
    _save_session_json(state, report_text)
    return {"pm_report_text": report_text}
