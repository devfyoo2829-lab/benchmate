"""
Knowledge 파이프라인 E2E 테스트 (fin_001 단일 문항)

조건:
- eval_mode: "knowledge"
- domain: "finance"
- selected_models: ["solar-pro"]
- data/questions/finance.json 에서 fin_001만 사용
- 파이프라인 전체 실행 후 knowledge_scores_ab, pm_report_text 출력
"""

import json
import os
import sys
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.graph import build_graph
from pipeline.state import EvalState

# ── 테스트용 데이터 상수 ─────────────────────────────────────────────────────────

_FIN_001 = {
    "id": "fin_001",
    "domain": "finance",
    "question": "신용대출 금리 산정 시 고려하는 주요 요소 3가지를 설명하시오.",
    "reference_answer": (
        "신용대출 금리는 기준금리(COFIX), 신용등급, 가산금리의 세 요소로 결정된다. "
        "COFIX는 은행의 자금조달 비용을 반영한 기준금리이며, 신용등급이 높을수록 "
        "가산금리가 낮아진다. 최종 대출 금리는 기준금리에 가산금리를 더한 값으로 산출된다."
    ),
    "instance_rubric": (
        "COFIX, 신용등급, 가산금리 세 가지를 모두 언급했는가? "
        "신용등급과 가산금리의 반비례 관계를 명시했는가? "
        "최종 금리 계산 구조(기준금리 + 가산금리)를 설명했는가?"
    ),
    "difficulty": "medium",
    "task_type": "explanation",
}


# ── Judge 목업 (HF_TOKEN 없이 실행 가능하도록) ────────────────────────────────────

_JUDGE_JSON_RESPONSE = json.dumps({
    "accuracy": 4,
    "fluency": 5,
    "hallucination": 5,
    "domain_expertise": 4,
    "utility": 4,
    "total": 22,
    "reason": (
        "COFIX, 신용등급, 가산금리 세 요소를 모두 정확히 언급했으며 "
        "금리 구조 설명이 명확합니다. 전문 용어 사용이 적절합니다."
    ),
})


def _mock_load_json(path: str) -> object:
    """_load_json 목업: fin_001만 포함한 최소 데이터 반환."""
    if "questions" in path:
        return {"domain": "finance", "questions": [_FIN_001]}
    elif "tools" in path:
        return {"domain": "finance", "tools": []}
    elif "scenarios" in path:
        return {"domain": "finance", "scenarios": []}
    return {}


# ── 초기 EvalState ────────────────────────────────────────────────────────────────

def _make_initial_state() -> EvalState:
    return {
        "eval_mode": "knowledge",
        "domain": "finance",
        "selected_models": ["solar-pro"],
        # 아래 필드는 load_scenarios 노드가 채움
        "questions": [],
        "scenarios": [],
        "available_tools": [],
        "rubric_text": "",
        "model_responses": [],
        "knowledge_scores_ab": [],
        "knowledge_scores_ba": [],
        "knowledge_scores_final": [],
        "agent_scores": [],
        "retry_count": 0,
        "last_failed_branch": None,
        "_retry_targets": [],
        "human_review_queue": [],
        "judge_reliability": None,
        "summary_table": None,
        "estimated_cost": None,
        "pm_report_text": None,
        "eval_session_id": "",
    }


# ── E2E 테스트 ────────────────────────────────────────────────────────────────────

def test_knowledge_e2e():
    """
    Knowledge 파이프라인 전체 실행 테스트.

    실행 순서:
    load_scenarios → route_mode → generate_responses → judge_knowledge →
    validate_scores → flag_human_review → aggregate_results → generate_report
    """
    graph = build_graph()
    initial_state = _make_initial_state()

    # HF_TOKEN 없이 실행:
    #   - _call_qwen: Judge 목업 (solar-pro로 generate_responses는 실제 API 호출)
    #   - _generate_report_text: GPT-4o 실패 시 Qwen 폴백 방지용 목업
    _report_mock = AsyncMock(return_value=(
        "# 금융 도메인 LLM 평가 리포트 (E2E 테스트)\n\n"
        "## 1. 평가 요약\n"
        "solar-pro 모델을 금융 도메인 Knowledge 1문항으로 평가하였습니다.\n\n"
        "## 2. 종합 추천 모델\nsolar-pro — Knowledge total 22/25 달성.\n"
    ))

    with (
        patch("pipeline.nodes.load_scenarios._load_json", side_effect=_mock_load_json),
        patch(
            "pipeline.nodes.judge_knowledge._call_qwen",
            new=AsyncMock(return_value=_JUDGE_JSON_RESPONSE),
        ),
        patch(
            "pipeline.nodes.generate_report._generate_report_text",
            new=_report_mock,
        ),
    ):
        final_state = graph.invoke(initial_state)

    # ── 출력 ──────────────────────────────────────────────────────────────────────
    print("\n\n" + "=" * 60)
    print("=== knowledge_scores_ab ===")
    print("=" * 60)
    print(json.dumps(final_state.get("knowledge_scores_ab", []), ensure_ascii=False, indent=2))

    print("\n" + "=" * 60)
    print("=== pm_report_text ===")
    print("=" * 60)
    print(final_state.get("pm_report_text") or "(없음)")

    # ── 검증 ──────────────────────────────────────────────────────────────────────
    scores_ab = final_state.get("knowledge_scores_ab", [])
    assert scores_ab, "knowledge_scores_ab가 비어있습니다"

    score = scores_ab[0]
    assert score["question_id"] == "fin_001", f"예상 question_id: fin_001, 실제: {score['question_id']}"
    assert score["model_name"] == "solar-pro", f"예상 model_name: solar-pro, 실제: {score['model_name']}"
    assert 5 <= score["total"] <= 25, f"total 점수 범위 이탈 (5~25): {score['total']}"

    assert final_state.get("pm_report_text"), "pm_report_text가 비어있습니다"


if __name__ == "__main__":
    test_knowledge_e2e()
