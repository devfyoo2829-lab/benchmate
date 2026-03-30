"""
BenchMate — Screen 5: 결과 대시보드
"""

from __future__ import annotations

import streamlit as st
import plotly.graph_objects as go


# ── 상수 ──────────────────────────────────────────────────────────────────────

_KNOWLEDGE_AXES = [
    "사실 정확도",
    "한국어 자연성",
    "잘못된 정보\n생성 여부",
    "도메인 전문성",
    "응답 적절성",
]

_KNOWLEDGE_KEYS = ["accuracy", "fluency", "hallucination", "domain_expertise", "utility"]

_AGENT_ITEMS = ["call", "slot", "relevance", "completion"]
_AGENT_LABELS = {
    "call":       "Tool 호출 정확도",
    "slot":       "슬롯 요청 적절성",
    "relevance":  "거절 적절성",
    "completion": "결과 전달 품질",
}

_MODEL_COLORS = [
    "#4F8EF7",  # blue
    "#F7844F",  # orange
    "#4FD1C5",  # teal
    "#F7C94F",  # yellow
    "#A78BFA",  # purple
]


# ── 데이터 추출 헬퍼 ──────────────────────────────────────────────────────────

def _extract_model_stats(eval_result: dict) -> dict[str, dict]:
    """
    summary_table 또는 raw 점수 목록에서 모델별 통계를 추출한다.
    반환: {model_name: {knowledge_total, knowledge_axes, agent_scores}}
    """
    summary_table: dict | None = eval_result.get("summary_table")
    stats: dict[str, dict] = {}

    if summary_table:
        for model_name, domains in summary_table.items():
            # 도메인 전체 평균
            k_totals: list[float] = []
            k_axes: dict[str, list[float]] = {k: [] for k in _KNOWLEDGE_KEYS}
            a_scores: dict[str, list[float]] = {k: [] for k in _AGENT_ITEMS}

            for domain_data in domains.values():
                if isinstance(domain_data, dict):
                    # Knowledge 점수
                    for key in _KNOWLEDGE_KEYS:
                        val = domain_data.get(key)
                        if val is not None:
                            k_axes[key].append(float(val))
                    total = domain_data.get("total") or domain_data.get("knowledge_total")
                    if total is not None:
                        k_totals.append(float(total))
                    # Agent 점수
                    for key in _AGENT_ITEMS:
                        val = domain_data.get(f"{key}_score")
                        if val is not None:
                            a_scores[key].append(float(val))

            stats[model_name] = {
                "knowledge_total": (sum(k_totals) / len(k_totals)) if k_totals else 0.0,
                "knowledge_axes": {
                    k: (sum(v) / len(v)) if v else 0.0 for k, v in k_axes.items()
                },
                "agent_scores": {
                    k: (sum(v) / len(v)) if v else 0.0 for k, v in a_scores.items()
                },
            }
        return stats

    # summary_table 없을 때 — knowledge_scores_final 과 agent_scores 에서 직접 집계
    k_final: list[dict] = eval_result.get("knowledge_scores_final") or []
    a_raw: list[dict] = eval_result.get("agent_scores") or []

    for record in k_final:
        model = record.get("model_name", "unknown")
        if model not in stats:
            stats[model] = {
                "knowledge_total": 0.0,
                "knowledge_axes": {k: 0.0 for k in _KNOWLEDGE_KEYS},
                "agent_scores": {k: 0.0 for k in _AGENT_ITEMS},
                "_k_counts": 0,
                "_k_axes_acc": {k: [] for k in _KNOWLEDGE_KEYS},
            }
        for key in _KNOWLEDGE_KEYS:
            stats[model]["_k_axes_acc"][key].append(float(record.get(key, 0)))
        stats[model]["_k_counts"] += 1

    for model, data in stats.items():
        counts = data.pop("_k_counts", 0)
        acc = data.pop("_k_axes_acc", {})
        if counts:
            data["knowledge_total"] = sum(
                sum(v) / len(v) for v in acc.values() if v
            )
            data["knowledge_axes"] = {
                k: (sum(v) / len(v)) if v else 0.0 for k, v in acc.items()
            }

    for record in a_raw:
        model = record.get("model_name", "unknown")
        if model not in stats:
            stats[model] = {
                "knowledge_total": 0.0,
                "knowledge_axes": {k: 0.0 for k in _KNOWLEDGE_KEYS},
                "agent_scores": {k: 0.0 for k in _AGENT_ITEMS},
            }
        for key in _AGENT_ITEMS:
            field = f"{key}_score"
            val = record.get(field)
            if val is not None:
                prev = stats[model]["agent_scores"].get(key, [])
                if not isinstance(prev, list):
                    prev = [prev] if prev else []
                prev.append(float(val))
                stats[model]["agent_scores"][key] = prev

    # 리스트 → 평균
    for model in stats:
        for key in _AGENT_ITEMS:
            val = stats[model]["agent_scores"].get(key, 0.0)
            if isinstance(val, list):
                stats[model]["agent_scores"][key] = (sum(val) / len(val)) if val else 0.0

    return stats


def _agent_call_avg(agent_scores: dict[str, float]) -> float:
    """call_score 평균 (0~1)."""
    return agent_scores.get("call", 0.0)


# ── 지표 카드 ─────────────────────────────────────────────────────────────────

def _render_metric_cards(eval_result: dict, model_stats: dict[str, dict]) -> None:
    c1, c2, c3 = st.columns(3)

    with c1:
        st.metric("평가 모델 수", f"{len(model_stats)}개")

    with c2:
        reliability = eval_result.get("judge_reliability")
        if reliability is not None:
            st.metric("Judge 신뢰도", f"{reliability:.1f}%")
        else:
            st.metric("Judge 신뢰도", "측정 전")

    with c3:
        cost_dict: dict | None = eval_result.get("estimated_cost")
        if cost_dict:
            total_cost = cost_dict.get("_total") or sum(
                v for k, v in cost_dict.items() if k != "_total" and isinstance(v, (int, float))
            )
            st.metric("총 평가 비용", f"${total_cost:.4f}")
        else:
            st.metric("총 평가 비용", "—")


# ── 산점도 ────────────────────────────────────────────────────────────────────

def _render_scatter(model_stats: dict[str, dict]) -> None:
    st.subheader("Knowledge vs Agent 비교")

    fig = go.Figure()

    for i, (model, data) in enumerate(model_stats.items()):
        color = _MODEL_COLORS[i % len(_MODEL_COLORS)]
        x = data["knowledge_total"]           # 0~25
        y = _agent_call_avg(data["agent_scores"])  # 0~1

        fig.add_trace(go.Scatter(
            x=[x],
            y=[y],
            mode="markers+text",
            name=model,
            text=[model],
            textposition="top center",
            marker=dict(size=18, color=color, line=dict(width=1.5, color="white")),
        ))

    fig.update_layout(
        xaxis=dict(title="Knowledge 총점 (0~25)", range=[-1, 26]),
        yaxis=dict(title="Agent call_score 평균 (0~1)", range=[-0.05, 1.1]),
        height=420,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=40, r=40, t=40, b=40),
    )

    st.plotly_chart(fig, use_container_width=True)


# ── 레이더 차트 ───────────────────────────────────────────────────────────────

def _render_radar(model_stats: dict[str, dict]) -> None:
    st.subheader("Knowledge 세부 항목 비교")

    fig = go.Figure()

    for i, (model, data) in enumerate(model_stats.items()):
        color = _MODEL_COLORS[i % len(_MODEL_COLORS)]
        axes = data["knowledge_axes"]
        values = [axes.get(k, 0.0) for k in _KNOWLEDGE_KEYS]
        values_closed = values + [values[0]]  # 닫힌 다각형

        fig.add_trace(go.Scatterpolar(
            r=values_closed,
            theta=_KNOWLEDGE_AXES + [_KNOWLEDGE_AXES[0]],
            fill="toself",
            name=model,
            line=dict(color=color),
            fillcolor=color,
            opacity=0.25,
        ))

    fig.update_layout(
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 5]),
        ),
        height=420,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=40, r=40, t=40, b=40),
    )

    st.plotly_chart(fig, use_container_width=True)


# ── Agent 바 차트 ─────────────────────────────────────────────────────────────

def _render_agent_bar(model_stats: dict[str, dict]) -> None:
    st.subheader("Agent 항목별 비교")

    fig = go.Figure()

    for i, (model, data) in enumerate(model_stats.items()):
        color = _MODEL_COLORS[i % len(_MODEL_COLORS)]
        a_scores = data["agent_scores"]
        y_vals = [a_scores.get(k, 0.0) for k in _AGENT_ITEMS]
        x_labels = [_AGENT_LABELS[k] for k in _AGENT_ITEMS]

        fig.add_trace(go.Bar(
            name=model,
            x=x_labels,
            y=y_vals,
            marker_color=color,
        ))

    fig.update_layout(
        barmode="group",
        yaxis=dict(title="점수", range=[0, 1.1]),
        height=380,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=40, r=40, t=40, b=40),
    )

    st.plotly_chart(fig, use_container_width=True)


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

    model_stats = _extract_model_stats(eval_result)

    if not model_stats:
        _render_empty_state()
        return

    # ── 지표 카드 ──────────────────────────────────────────────────────────────
    _render_metric_cards(eval_result, model_stats)
    st.divider()

    # ── 산점도 ─────────────────────────────────────────────────────────────────
    _render_scatter(model_stats)
    st.divider()

    # ── 레이더 + Agent 바 ──────────────────────────────────────────────────────
    col_left, col_right = st.columns(2)
    with col_left:
        _render_radar(model_stats)
    with col_right:
        _render_agent_bar(model_stats)

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
