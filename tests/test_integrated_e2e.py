"""
Integrated 파이프라인 E2E 테스트

조건:
- eval_mode: "integrated"
- domain: "finance"
- selected_models: ["solar-pro"]
- Knowledge 1문항 + Agent 1시나리오 동시 평가
- 파이프라인 전체 실행 후 knowledge_scores_final, agent_scores 모두 검증
- HF_TOKEN / OPENAI_API_KEY 없이 전 구간 Mock 처리
"""

import json
import os
import sys
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.graph import build_graph
from pipeline.state import EvalState

# ── 테스트 데이터 ────────────────────────────────────────────────────────────────

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
        "신용등급과 가산금리의 반비례 관계를 명시했는가?"
    ),
    "difficulty": "medium",
    "task_type": "explanation",
}

_FIN_TOOL = {
    "name": "search_loan_rate",
    "description": "고객 ID와 신용점수를 입력받아 적용 가능한 대출 금리를 조회합니다.",
    "parameters": [
        {"name": "customer_id", "type": "string", "required": True, "description": "고객 고유 식별자"},
        {"name": "credit_score", "type": "integer", "required": True, "description": "신용점수 300~850"},
    ],
    "mock_return": {
        "customer_id": "C-1234",
        "credit_score": 720,
        "credit_grade": "2등급",
        "final_rate": 4.7,
        "max_loan_limit": 50000000,
    },
}

_FIN_SC_001 = {
    "id": "fin_sc_001",
    "domain": "finance",
    "scenario_type": "single_A",
    "turns": [
        {
            "turn_index": 0,
            "role": "user",
            "content": "고객 ID C-1234의 신용대출 금리를 조회해주세요. 신용점수는 720점입니다.",
        },
        {
            "turn_index": 1,
            "role": "tool_result",
            "content": {
                "customer_id": "C-1234",
                "credit_score": 720,
                "credit_grade": "2등급",
                "final_rate": 4.7,
                "max_loan_limit": 50000000,
            },
        },
    ],
    "expected_tool_calls": [
        {
            "turn_index": 0,
            "tool_name": "search_loan_rate",
            "parameters": {"customer_id": "C-1234", "credit_score": 720},
        }
    ],
    "context_dependency": [],
    "available_tools": ["search_loan_rate"],
}

# ── Mock 응답 ────────────────────────────────────────────────────────────────────

_KNOWLEDGE_JUDGE_JSON = json.dumps({
    "accuracy": 4,
    "fluency": 5,
    "hallucination": 5,
    "domain_expertise": 4,
    "utility": 4,
    "total": 22,
    "reason": "COFIX, 신용등급, 가산금리 세 요소를 정확히 설명하였습니다.",
})

_AGENT_JUDGE_JSON = json.dumps({
    "score": 3,
    "reason": "대출 금리 조회 결과를 고객에게 명확하게 전달하였습니다.",
})

_UPSTAGE_TOOL_CALL_RESPONSE = {
    "text": json.dumps({
        "tool_name": "search_loan_rate",
        "parameters": {"customer_id": "C-1234", "credit_score": 720},
    }),
    "input_tokens": 120,
    "output_tokens": 35,
}


def _mock_load_json(path: str) -> object:
    if "questions" in path:
        return {"domain": "finance", "questions": [_FIN_001]}
    elif "tools" in path:
        return {"domain": "finance", "tools": [_FIN_TOOL]}
    elif "scenarios" in path:
        return {"domain": "finance", "scenarios": [_FIN_SC_001]}
    return {}


# ── 초기 EvalState ───────────────────────────────────────────────────────────────

def _make_initial_state() -> EvalState:
    return {
        "eval_mode": "integrated",
        "domain": "finance",
        "selected_models": ["solar-pro"],
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


# ── E2E 테스트 ───────────────────────────────────────────────────────────────────

def test_integrated_e2e():
    """
    Integrated 파이프라인 전체 실행 테스트.

    실행 순서 (두 페이즈):
    [Knowledge 페이즈]
    load_scenarios → route_mode(_integrated_phase="knowledge")
      → generate_responses → judge_knowledge → validate_scores
      → flag_human_review → aggregate_results(_integrated_phase="agent")

    [Agent 페이즈]
      → generate_tool_calls → evaluate_call → judge_agent → validate_scores
      → flag_human_review → aggregate_results(_integrated_phase="done")
      → generate_report → END

    검증:
    - knowledge_scores_final 비어있지 않음
    - agent_scores 비어있지 않음  ← 핵심: 이전에는 이 검증이 실패했음
    - pm_report_text 존재
    """
    graph = build_graph()
    initial_state = _make_initial_state()

    _report_mock = AsyncMock(return_value=(
        "# 금융 도메인 LLM 평가 리포트 (Integrated E2E 테스트)\n\n"
        "## 종합 추천 모델\nsolar-pro — Knowledge 22/25, Agent call_score 1/1.\n"
    ))

    with (
        patch("pipeline.nodes.load_scenarios._load_json", side_effect=_mock_load_json),
        patch(
            "pipeline.nodes.judge_knowledge._call_qwen",
            new=AsyncMock(return_value=_KNOWLEDGE_JUDGE_JSON),
        ),
        patch(
            "pipeline.nodes.generate_tool_calls._call_upstage",
            new=AsyncMock(return_value=_UPSTAGE_TOOL_CALL_RESPONSE),
        ),
        patch(
            "pipeline.nodes.judge_agent._call_qwen",
            new=AsyncMock(return_value=_AGENT_JUDGE_JSON),
        ),
        patch(
            "pipeline.nodes.generate_report._generate_report_text",
            new=_report_mock,
        ),
    ):
        final_state = graph.invoke(initial_state)

    # ── 출력 ─────────────────────────────────────────────────────────────────────
    print("\n\n" + "=" * 60)
    print("=== knowledge_scores_final ===")
    print("=" * 60)
    print(json.dumps(final_state.get("knowledge_scores_final", []), ensure_ascii=False, indent=2))

    print("\n" + "=" * 60)
    print("=== agent_scores ===")
    print("=" * 60)
    print(json.dumps(final_state.get("agent_scores", []), ensure_ascii=False, indent=2))

    print("\n" + "=" * 60)
    print("=== summary_table ===")
    print("=" * 60)
    print(json.dumps(final_state.get("summary_table"), ensure_ascii=False, indent=2))

    print("\n" + "=" * 60)
    print("=== pm_report_text ===")
    print("=" * 60)
    print(final_state.get("pm_report_text") or "(없음)")

    # ── 검증 ─────────────────────────────────────────────────────────────────────
    # Knowledge 경로 검증
    k_scores = final_state.get("knowledge_scores_final", [])
    assert k_scores, "knowledge_scores_final이 비어있습니다 (Knowledge 경로 미실행)"

    k = k_scores[0]
    assert k["question_id"] == "fin_001", f"예상 question_id: fin_001, 실제: {k['question_id']}"
    assert k["model_name"] == "solar-pro"
    assert 5 <= k["total"] <= 25, f"total 범위 이탈 (5~25): {k['total']}"

    # Agent 경로 검증 (이전에 실패하던 핵심 검증)
    a_scores = final_state.get("agent_scores", [])
    assert a_scores, "agent_scores가 비어있습니다 (Agent 경로 미실행 — integrated 분기 버그)"

    a = a_scores[0]
    assert a["scenario_id"] == "fin_sc_001", f"예상 scenario_id: fin_sc_001, 실제: {a['scenario_id']}"
    assert a["model_name"] == "solar-pro"
    assert a["call_score"] == 1, f"call_score=1 예상, 실제: {a['call_score']}"
    assert a.get("completion_score") is not None, "completion_score가 None (judge_agent 미실행)"

    # summary_table: Knowledge + Agent 둘 다 채워져 있어야 함
    summary = final_state.get("summary_table", {})
    assert summary, "summary_table이 비어있습니다"
    solar = summary.get("solar-pro", {})
    assert solar.get("knowledge", {}).get("question_count", 0) > 0, \
        "summary_table에 knowledge 데이터 없음"
    assert solar.get("agent", {}).get("scenario_count", 0) > 0, \
        "summary_table에 agent 데이터 없음"

    assert final_state.get("pm_report_text"), "pm_report_text가 비어있습니다"

    print("\n✓ Integrated E2E 테스트 통과 — Knowledge + Agent 경로 모두 실행됨")


if __name__ == "__main__":
    test_integrated_e2e()
