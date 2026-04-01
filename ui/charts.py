"""
BenchMate — ui/charts.py
모델 통계 추출 및 Plotly 차트 빌더.
screen5_dashboard와 screen7_report 양쪽에서 공용으로 사용한다.
"""

from __future__ import annotations

import plotly.graph_objects as go

# ── 상수 ──────────────────────────────────────────────────────────────────────

KNOWLEDGE_AXES = [
    "사실 정확도", "한국어 자연성", "허위 정보 없음", "도메인 전문성", "응답 적절성",
]
KNOWLEDGE_KEYS = ["accuracy", "fluency", "hallucination", "domain_expertise", "utility"]
AGENT_ITEMS    = ["call", "slot", "relevance", "completion"]
AGENT_LABELS   = {
    "call":       "Tool 호출 정확도",
    "slot":       "슬롯 요청 적절성",
    "relevance":  "거절 적절성",
    "completion": "결과 전달 품질",
}
MODEL_COLORS = ["#4F8EF7", "#F7844F", "#4FD1C5", "#F7C94F", "#A78BFA"]
MODEL_DISPLAY_NAMES: dict[str, str] = {
    "solar-pro":     "Solar Pro",
    "gpt-4o":        "GPT-4o",
    "claude-sonnet": "Claude Sonnet",
}

_AGENT_MODES = {"agent", "integrated", "종합 평가", "업무 자동화 능력 평가"}


# ── 모델 통계 추출 ────────────────────────────────────────────────────────────

def extract_model_stats(eval_result: dict) -> dict[str, dict]:
    """
    summary_table 또는 raw 점수 목록에서 모델별 통계를 추출한다.
    반환: {model_name: {knowledge_total, knowledge_axes, agent_scores,
                        has_knowledge, has_agent}}
    """
    summary_table: dict | None = eval_result.get("summary_table")
    stats: dict[str, dict] = {}

    if summary_table:
        for model_name, sections in summary_table.items():
            k: dict = sections.get("knowledge") or {}
            a: dict = sections.get("agent") or {}

            total_raw = k.get("total")
            stats[model_name] = {
                "knowledge_total": float(total_raw) if total_raw is not None else 0.0,
                "knowledge_axes": {
                    key: float(k[key]) if k.get(key) is not None else 0.0
                    for key in KNOWLEDGE_KEYS
                },
                "agent_scores": {
                    key: float(a[f"{key}_score"]) if a.get(f"{key}_score") is not None else 0.0
                    for key in AGENT_ITEMS
                },
                "has_knowledge": (k.get("question_count") or 0) > 0,
                "has_agent":     (a.get("scenario_count") or 0) > 0,
            }
        return stats

    # summary_table 없을 때 — raw 목록에서 직접 집계
    k_final: list[dict] = eval_result.get("knowledge_scores_final") or []
    a_raw:   list[dict] = eval_result.get("agent_scores") or []

    for record in k_final:
        model = record.get("model_name", "unknown")
        if model not in stats:
            stats[model] = {
                "knowledge_total": 0.0,
                "knowledge_axes":  {k: 0.0 for k in KNOWLEDGE_KEYS},
                "agent_scores":    {k: 0.0 for k in AGENT_ITEMS},
                "has_knowledge": False,
                "has_agent":     False,
                "_acc": {k: [] for k in KNOWLEDGE_KEYS},
            }
        for key in KNOWLEDGE_KEYS:
            stats[model]["_acc"][key].append(float(record.get(key, 0)))
        stats[model]["has_knowledge"] = True

    for model, data in stats.items():
        acc = data.pop("_acc", {})
        if acc:
            axes = {k: (sum(v) / len(v)) if v else 0.0 for k, v in acc.items()}
            data["knowledge_axes"]  = axes
            data["knowledge_total"] = sum(axes.values())

    for record in a_raw:
        model = record.get("model_name", "unknown")
        if model not in stats:
            stats[model] = {
                "knowledge_total": 0.0,
                "knowledge_axes":  {k: 0.0 for k in KNOWLEDGE_KEYS},
                "agent_scores":    {k: 0.0 for k in AGENT_ITEMS},
                "has_knowledge": False,
                "has_agent":     False,
            }
        for key in AGENT_ITEMS:
            val = record.get(f"{key}_score")
            if val is not None:
                prev = stats[model]["agent_scores"].get(key, [])
                if not isinstance(prev, list):
                    prev = [prev] if prev else []
                prev.append(float(val))
                stats[model]["agent_scores"][key] = prev
                stats[model]["has_agent"] = True

    for model in stats:
        for key in AGENT_ITEMS:
            val = stats[model]["agent_scores"].get(key, 0.0)
            if isinstance(val, list):
                stats[model]["agent_scores"][key] = (sum(val) / len(val)) if val else 0.0

    return stats


def has_knowledge_data(model_stats: dict[str, dict]) -> bool:
    return any(d.get("has_knowledge") for d in model_stats.values())


def has_agent_data(
    model_stats: dict[str, dict],
    eval_result: dict | None = None,
    session_eval_mode: str = "",
) -> bool:
    """
    model_stats 플래그 우선 확인 → eval_mode 폴백.
    session_eval_mode: st.session_state.get("eval_mode", "") 값
    """
    # 1. summary_table 기반 플래그 (가장 신뢰 가능)
    if any(d.get("has_agent") for d in model_stats.values()):
        return True
    # 2. eval_mode 기반 (eval_result 및 session_state 모두 확인)
    mode_er = (eval_result or {}).get("eval_mode", "")
    if mode_er in _AGENT_MODES or session_eval_mode in _AGENT_MODES:
        # agent_scores가 실제로 존재하는지 체크
        if eval_result and eval_result.get("agent_scores"):
            return True
        summary = (eval_result or {}).get("summary_table") or {}
        if any(v.get("agent", {}).get("scenario_count", 0) > 0 for v in summary.values()):
            return True
    return False


# ── 차트 빌더 ─────────────────────────────────────────────────────────────────

def build_scatter_fig(model_stats: dict[str, dict]) -> go.Figure:
    """Knowledge vs Agent 산점도."""
    fig = go.Figure()
    for i, (model, data) in enumerate(model_stats.items()):
        color = MODEL_COLORS[i % len(MODEL_COLORS)]
        fig.add_trace(go.Scatter(
            x=[data["knowledge_total"]],
            y=[data["agent_scores"].get("call", 0.0)],
            mode="markers+text",
            name=MODEL_DISPLAY_NAMES.get(model, model),
            text=[MODEL_DISPLAY_NAMES.get(model, model)],
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
    return fig


def build_knowledge_bar_fig(model_stats: dict[str, dict]) -> go.Figure:
    """Knowledge 총점 바 차트."""
    models = [m for m, d in model_stats.items() if d.get("has_knowledge")]
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=[MODEL_DISPLAY_NAMES.get(m, m) for m in models],
        y=[model_stats[m]["knowledge_total"] for m in models],
        marker_color=[MODEL_COLORS[i % len(MODEL_COLORS)] for i in range(len(models))],
        text=[f"{model_stats[m]['knowledge_total']:.1f}" for m in models],
        textposition="outside",
    ))
    fig.update_layout(
        yaxis=dict(title="Knowledge 총점 (0~25)", range=[0, 28]),
        height=380,
        margin=dict(l=40, r=40, t=40, b=40),
        showlegend=False,
    )
    return fig


def build_radar_fig(model_stats: dict[str, dict]) -> go.Figure | None:
    """Knowledge 세부 레이더 차트. 데이터 없으면 None."""
    fig = go.Figure()
    plotted = False
    for i, (model, data) in enumerate(model_stats.items()):
        axes  = data["knowledge_axes"]
        vals  = [axes.get(k, 0.0) for k in KNOWLEDGE_KEYS]
        if all(v == 0.0 for v in vals):
            continue
        color = MODEL_COLORS[i % len(MODEL_COLORS)]
        fig.add_trace(go.Scatterpolar(
            r=vals + [vals[0]],
            theta=KNOWLEDGE_AXES + [KNOWLEDGE_AXES[0]],
            fill="toself",
            name=MODEL_DISPLAY_NAMES.get(model, model),
            line=dict(color=color),
            fillcolor=color,
            opacity=0.25,
        ))
        plotted = True
    if not plotted:
        return None
    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, 5])),
        height=420,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=40, r=40, t=40, b=40),
    )
    return fig


def build_agent_bar_fig(model_stats: dict[str, dict]) -> go.Figure | None:
    """Agent 항목별 바 차트. 데이터 없으면 None."""
    traces = []
    for i, (model, data) in enumerate(model_stats.items()):
        if not data.get("has_agent"):
            continue
        a = data["agent_scores"]
        traces.append(go.Bar(
            name=MODEL_DISPLAY_NAMES.get(model, model),
            x=[AGENT_LABELS[k] for k in AGENT_ITEMS],
            y=[a.get(k, 0.0) for k in AGENT_ITEMS],
            marker_color=MODEL_COLORS[i % len(MODEL_COLORS)],
        ))
    if not traces:
        return None
    fig = go.Figure(data=traces)
    fig.update_layout(
        barmode="group",
        yaxis=dict(title="점수", range=[0, 1.1]),
        height=380,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=40, r=40, t=40, b=40),
    )
    return fig


def fig_to_png(fig: go.Figure) -> bytes | None:
    """Plotly Figure → PNG bytes (kaleido). 실패 시 None."""
    try:
        return fig.to_image(format="png", width=800, height=450)
    except Exception:
        return None
