"""
Agent 파이프라인 E2E 테스트 (fin_sc_001 단일 시나리오)

조건:
- eval_mode: "agent"
- domain: "finance"
- selected_models: ["solar-pro"]
- data/scenarios/finance_scenarios.json 없으면 single_A 시나리오 1개를 임시 생성
- 파이프라인 전체 실행 후 agent_scores, call_score 출력
- HF_TOKEN 없으면 judge_agent는 Mock으로 대체
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

_FIN_TOOL_SEARCH_LOAN_RATE = {
    "name": "search_loan_rate",
    "description": "고객 ID와 신용점수를 입력받아 적용 가능한 대출 금리를 조회합니다.",
    "parameters": [
        {
            "name": "customer_id",
            "type": "string",
            "required": True,
            "description": "고객 고유 식별자. 예: C-1234",
        },
        {
            "name": "credit_score",
            "type": "integer",
            "required": True,
            "description": "신용점수. 300~850 범위. 높을수록 우량 고객",
        },
    ],
    "mock_return": {
        "customer_id": "C-1234",
        "credit_score": 720,
        "credit_grade": "2등급",
        "final_rate": 4.7,
        "max_loan_limit": 50000000,
    },
}

# single_A 시나리오: 정상 Tool 호출 (search_loan_rate)
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
            "parameters": {
                "customer_id": "C-1234",
                "credit_score": 720,
            },
        }
    ],
    "context_dependency": [],
    "available_tools": ["search_loan_rate"],
}

# ── Judge 목업 (HF_TOKEN 없이 실행 가능하도록) ────────────────────────────────────

_AGENT_JUDGE_JSON = json.dumps({
    "score": 3,
    "reason": (
        "고객에게 대출 금리 조회 결과(4.7%)를 정확하게 전달하였으며, "
        "신용등급과 최대 대출 한도까지 포함하여 충분한 정보를 제공하였습니다."
    ),
})

# ── 모델 응답 목업 (Upstage API 호출 대체) ────────────────────────────────────────

# solar-pro가 반환할 Tool 호출 JSON (expected_tool_calls와 일치 → call_score=1)
_UPSTAGE_TOOL_CALL_RESPONSE = {
    "text": json.dumps({
        "tool_name": "search_loan_rate",
        "parameters": {
            "customer_id": "C-1234",
            "credit_score": 720,
        },
    }),
    "input_tokens": 120,
    "output_tokens": 35,
}


# ── _load_json 목업 ────────────────────────────────────────────────────────────

def _mock_load_json(path: str) -> object:
    """_load_json 목업: 테스트용 최소 데이터 반환."""
    if "questions" in path:
        return {"domain": "finance", "questions": []}
    elif "tools" in path:
        return {"domain": "finance", "tools": [_FIN_TOOL_SEARCH_LOAN_RATE]}
    elif "scenarios" in path:
        return {"domain": "finance", "scenarios": [_FIN_SC_001]}
    return {}


# ── 초기 EvalState ─────────────────────────────────────────────────────────────

def _make_initial_state() -> EvalState:
    return {
        "eval_mode": "agent",
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


# ── E2E 테스트 ─────────────────────────────────────────────────────────────────

def test_agent_e2e():
    """
    Agent 파이프라인 전체 실행 테스트.

    실행 순서:
    load_scenarios → route_mode → generate_tool_calls → evaluate_call →
    judge_agent → validate_scores → flag_human_review →
    aggregate_results → generate_report
    """
    graph = build_graph()
    initial_state = _make_initial_state()

    _report_mock = AsyncMock(return_value=(
        "# 금융 도메인 LLM 평가 리포트 (Agent E2E 테스트)\n\n"
        "## 1. 평가 요약\n"
        "solar-pro 모델을 금융 도메인 Agent 시나리오 1건으로 평가하였습니다.\n\n"
        "## 2. 종합 추천 모델\nsolar-pro — call_score 1/1 달성.\n"
    ))

    with (
        patch("pipeline.nodes.load_scenarios._load_json", side_effect=_mock_load_json),
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

    # ── 출력 ──────────────────────────────────────────────────────────────────
    print("\n\n" + "=" * 60)
    print("=== agent_scores ===")
    print("=" * 60)
    print(json.dumps(final_state.get("agent_scores", []), ensure_ascii=False, indent=2))

    print("\n" + "=" * 60)
    print("=== call_score 요약 ===")
    print("=" * 60)
    for s in final_state.get("agent_scores", []):
        print(
            f"  시나리오: {s['scenario_id']} | 모델: {s['model_name']} "
            f"| call_score: {s['call_score']} "
            f"| completion_score: {s.get('completion_score')} "
            f"| reason: {s.get('reason', '')}"
        )

    print("\n" + "=" * 60)
    print("=== pm_report_text ===")
    print("=" * 60)
    print(final_state.get("pm_report_text") or "(없음)")

    # ── 검증 ──────────────────────────────────────────────────────────────────
    agent_scores = final_state.get("agent_scores", [])
    assert agent_scores, "agent_scores가 비어있습니다"

    score = agent_scores[0]
    assert score["scenario_id"] == "fin_sc_001", (
        f"예상 scenario_id: fin_sc_001, 실제: {score['scenario_id']}"
    )
    assert score["model_name"] == "solar-pro", (
        f"예상 model_name: solar-pro, 실제: {score['model_name']}"
    )
    assert score["call_score"] == 1, (
        f"call_score=1 예상 (Tool 이름·파라미터 정확 일치), 실제: {score['call_score']} ({score.get('reason')})"
    )
    assert score.get("completion_score") is not None, "completion_score가 None입니다 (judge_agent 미실행)"
    assert 1 <= score["completion_score"] <= 3, (
        f"completion_score 범위 이탈 (1~3): {score['completion_score']}"
    )

    assert final_state.get("pm_report_text"), "pm_report_text가 비어있습니다"


if __name__ == "__main__":
    test_agent_e2e()
