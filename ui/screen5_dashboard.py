"""
BenchMate — Screen 5: 결과 대시보드
"""

from __future__ import annotations

import streamlit as st

from ui.charts import (
    extract_model_stats,
    has_knowledge_data,
    has_agent_data,
    build_scatter_fig,
    build_knowledge_bar_fig,
    build_radar_fig,
    build_agent_bar_fig,
)


# ── 지표 카드 ─────────────────────────────────────────────────────────────────

def _render_metric_cards(eval_result: dict, model_stats: dict[str, dict]) -> None:
    c1, c2, c3 = st.columns(3)

    with c1:
        st.metric(label="평가 모델 수", value=f"{len(model_stats)}개")

    with c2:
        # session_state 우선, 없으면 eval_result 폴백
        reliability = (
            st.session_state.get("judge_reliability")
            or st.session_state.get("eval_result", {}).get("judge_reliability")
        )
        if reliability is not None:
            st.metric(
                label="채점 신뢰도",
                value=f"{reliability:.1f}%",
                help="Human Review 완료 후 최신 수치로 갱신됩니다.",
            )
        else:
            st.metric(
                label="채점 신뢰도",
                value="Human Review 후 측정",
                help="Human Review 화면에서 AI 채점을 검토하면 자동으로 계산됩니다.",
            )

    with c3:
        cost_dict: dict | None = eval_result.get("estimated_cost")
        if cost_dict:
            total_cost = cost_dict.get("_total") or sum(
                v for k, v in cost_dict.items() if k != "_total" and isinstance(v, (int, float))
            )
            st.metric(label="총 평가 비용", value=f"${total_cost:.4f}")
        else:
            st.metric(label="총 평가 비용", value="—")


# ── 빈 결과 화면 ──────────────────────────────────────────────────────────────

def _render_empty_state() -> None:
    st.info("아직 평가 결과가 없습니다. 평가를 먼저 실행해주세요.")
    if st.button("평가 시작하기", type="primary"):
        st.session_state["current_screen"] = 4
        st.rerun()


# ── render ────────────────────────────────────────────────────────────────────

def render() -> None:
    st.title("BenchMate")
    st.write("평가 결과 대시보드")
    st.divider()

    eval_result: dict | None = st.session_state.get("eval_result")

    if not eval_result:
        _render_empty_state()
        return

    model_stats = extract_model_stats(eval_result)

    if not model_stats:
        _render_empty_state()
        return

    # ── 지표 카드 ──────────────────────────────────────────────────────────────
    _render_metric_cards(eval_result, model_stats)
    st.divider()

    eval_mode = st.session_state.get("eval_mode", "")
    has_k = has_knowledge_data(model_stats)
    has_a = has_agent_data(model_stats, eval_result, eval_mode)

    # ── 상단 주요 차트: 데이터 조합에 따라 결정 ──────────────────────────────
    if has_k and has_a:
        st.subheader("Knowledge vs Agent 비교")
        st.plotly_chart(build_scatter_fig(model_stats), use_container_width=True)
    elif has_k:
        st.subheader("도메인 지식 평가 결과 (25점 만점)")
        st.plotly_chart(build_knowledge_bar_fig(model_stats), use_container_width=True)
        st.caption("점수가 높을수록 도메인 지식과 답변 품질이 우수합니다.")
    elif has_a:
        st.info("Knowledge 평가 데이터가 없습니다. Agent 결과만 표시합니다.")
    st.divider()

    # ── 레이더 + Agent 바 ──────────────────────────────────────────────────────
    if has_a:
        col_left, col_right = st.columns(2)
        with col_left:
            if has_k:
                st.subheader("Knowledge 세부 항목 비교")
                radar_fig = build_radar_fig(model_stats)
                if radar_fig:
                    st.plotly_chart(radar_fig, use_container_width=True)
                else:
                    st.info("Knowledge 세부 항목 데이터가 없습니다.")
            else:
                st.info("Knowledge 세부 항목 데이터가 없습니다.")
        with col_right:
            st.subheader("Agent 항목별 비교")
            agent_fig = build_agent_bar_fig(model_stats)
            if agent_fig:
                st.plotly_chart(agent_fig, use_container_width=True)
            else:
                st.info("Agent 평가 데이터가 없습니다.")
    else:
        if has_k:
            st.subheader("Knowledge 세부 항목 비교")
            radar_fig = build_radar_fig(model_stats)
            if radar_fig:
                st.plotly_chart(radar_fig, use_container_width=True)
            else:
                st.info("Knowledge 세부 항목 데이터가 없습니다.")
        st.caption(
            "업무 자동화 능력 평가 또는 종합 평가 모드에서 Agent 차트를 확인할 수 있습니다."
        )

    st.divider()

    # ── 하단 네비게이션 ────────────────────────────────────────────────────────
    col_prev, col_human, col_pm = st.columns([1, 1, 1])

    with col_prev:
        if st.button("← 이전", use_container_width=True):
            st.session_state["current_screen"] = 4
            st.rerun()

    with col_human:
        if st.button("Human Review →", use_container_width=True):
            st.session_state["current_screen"] = 6
            st.rerun()

    with col_pm:
        if st.button("PM 리포트 →", type="primary", use_container_width=True):
            st.session_state["current_screen"] = 7
            st.rerun()
