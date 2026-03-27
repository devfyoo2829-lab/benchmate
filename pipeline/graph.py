"""
BenchMate — LangGraph 파이프라인 조립
설계 기준: docs/BenchMate_Agent설계.md §2, §4
"""

from langgraph.graph import StateGraph, END

from pipeline.state import EvalState
from pipeline.nodes.load_scenarios import load_scenarios
from pipeline.nodes.route_mode import route_mode
from pipeline.nodes.generate_responses import generate_responses
from pipeline.nodes.generate_tool_calls import generate_tool_calls
from pipeline.nodes.judge_knowledge import judge_knowledge
from pipeline.nodes.evaluate_call import evaluate_call
from pipeline.nodes.judge_agent import judge_agent
from pipeline.nodes.validate_scores import validate_scores
from pipeline.nodes.flag_human_review import flag_human_review
from pipeline.nodes.aggregate_results import aggregate_results
from pipeline.nodes.generate_report import generate_report


# ── 분기 함수 ──────────────────────────────────────────────────────────────────


def decide_branch(state: EvalState) -> str:
    """route_mode 노드 이후 분기 결정.

    integrated 모드는 _integrated_phase 필드로 현재 단계를 추적한다.
      - phase == "knowledge" (기본값): generate_responses 먼저 실행
      - phase == "agent": generate_tool_calls로 진행
    """
    mode = state["eval_mode"]

    if mode == "knowledge":
        return "knowledge"
    elif mode == "agent":
        return "agent"
    elif mode == "integrated":
        phase = state.get("_integrated_phase", "knowledge")  # type: ignore[call-overload]
        if phase == "agent":
            return "agent"
        return "integrated_k"  # knowledge 단계 먼저
    else:
        # 알 수 없는 모드 — knowledge로 폴백 (설계서 §7 오류 처리 정책)
        return "knowledge"


def decide_retry(state: EvalState) -> str:
    """validate_scores 노드 이후 재시도 또는 진행 결정.

    retry_count > 0 이면 last_failed_branch를 보고 해당 Judge 노드로 복귀.
    그 외에는 flag_human_review로 진행.
    """
    if state["retry_count"] > 0:
        failed_branch = state.get("last_failed_branch")  # type: ignore[call-overload]
        if failed_branch == "knowledge":
            return "retry_knowledge"
        elif failed_branch == "agent":
            return "retry_agent"
    return "ok"


# ── 그래프 조립 ────────────────────────────────────────────────────────────────


def build_graph() -> StateGraph:
    graph = StateGraph(EvalState)

    # ── 노드 등록 ──────────────────────────────────────────────────────────────
    graph.add_node("load_scenarios", load_scenarios)
    graph.add_node("route_mode", route_mode)
    graph.add_node("generate_responses", generate_responses)
    graph.add_node("generate_tool_calls", generate_tool_calls)
    graph.add_node("judge_knowledge", judge_knowledge)
    graph.add_node("evaluate_call", evaluate_call)
    graph.add_node("judge_agent", judge_agent)
    graph.add_node("validate_scores", validate_scores)
    graph.add_node("flag_human_review", flag_human_review)
    graph.add_node("aggregate_results", aggregate_results)
    graph.add_node("generate_report", generate_report)

    # ── 엣지 정의 ──────────────────────────────────────────────────────────────
    graph.set_entry_point("load_scenarios")
    graph.add_edge("load_scenarios", "route_mode")

    # route_mode 조건부 분기
    graph.add_conditional_edges(
        "route_mode",
        decide_branch,
        {
            "knowledge":    "generate_responses",
            "agent":        "generate_tool_calls",
            "integrated_k": "generate_responses",  # integrated는 knowledge 먼저
        },
    )

    # Knowledge 경로
    graph.add_edge("generate_responses", "judge_knowledge")
    graph.add_edge("judge_knowledge", "validate_scores")

    # Agent 경로
    graph.add_edge("generate_tool_calls", "evaluate_call")
    graph.add_edge("evaluate_call", "judge_agent")
    graph.add_edge("judge_agent", "validate_scores")

    # validate_scores 재시도 분기
    graph.add_conditional_edges(
        "validate_scores",
        decide_retry,
        {
            "retry_knowledge": "judge_knowledge",
            "retry_agent":     "judge_agent",
            "ok":              "flag_human_review",
        },
    )

    # 하류 공통 경로
    graph.add_edge("flag_human_review", "aggregate_results")
    graph.add_edge("aggregate_results", "generate_report")
    graph.add_edge("generate_report", END)

    return graph.compile()
