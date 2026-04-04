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
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 5]),
            angularaxis=dict(tickfont=dict(size=9)),
        ),
        height=420,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=80, r=80, t=100, b=80),
    )
    return fig


_AGENT_ITEM_TO_KEY = {
    "call":       "call_score",
    "slot":       "slot_score",
    "relevance":  "relevance_score",
    "completion": "completion_score",
}


def build_agent_bar_fig(
    model_stats: dict[str, dict],
    summary_table: dict | None = None,
) -> go.Figure | None:
    """Agent 항목별 바 차트. 데이터 없으면 None.

    summary_table이 제공된 경우: 해당 항목이 None이 아닌 모델이
    하나라도 있는 항목만 x축에 표시한다.
    y축은 0과 1만 표시 (dtick=1).
    """
    # 표시할 항목 결정
    if summary_table:
        shown_items = [
            item for item in AGENT_ITEMS
            if any(
                (sections.get("agent") or {}).get(_AGENT_ITEM_TO_KEY[item]) is not None
                for sections in summary_table.values()
            )
        ]
    else:
        # summary_table 없으면 non-zero인 항목만 (전부 0이면 전체 표시)
        non_zero = [
            item for item in AGENT_ITEMS
            if any(
                (data.get("agent_scores") or {}).get(item, 0.0) != 0.0
                for data in model_stats.values()
                if data.get("has_agent")
            )
        ]
        shown_items = non_zero or list(AGENT_ITEMS)

    traces = []
    for i, (model, data) in enumerate(model_stats.items()):
        if not data.get("has_agent"):
            continue
        a = data["agent_scores"]
        traces.append(go.Bar(
            name=MODEL_DISPLAY_NAMES.get(model, model),
            x=[AGENT_LABELS[k] for k in shown_items],
            y=[a.get(k, 0.0) for k in shown_items],
            marker_color=MODEL_COLORS[i % len(MODEL_COLORS)],
        ))
    if not traces:
        return None
    fig = go.Figure(data=traces)
    fig.update_layout(
        barmode="group",
        yaxis=dict(
            title="점수",
            range=[-0.05, 1.2],
            dtick=1,
            tickvals=[0, 1],
        ),
        height=380,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=40, r=40, t=40, b=40),
    )
    return fig


def build_agent_heatmap_fig(
    model_stats: dict[str, dict],
    summary_table: dict | None = None,
) -> go.Figure | None:
    """Agent 항목별 히트맵.

    값 매핑:
      1      → z=1.0, "#22C55E" (초록), "✅ 성공"
      0      → z=0.0, "#EF4444" (빨강), "❌ 실패"
      None   → z=0.5, "#D1D5DB" (회색), "—"

    summary_table 기준으로 None인 항목 열 전체를 제거.
    데이터 없으면 None 반환.
    """
    models = [m for m, d in model_stats.items() if d.get("has_agent")]
    if not models:
        return None

    # 표시할 항목 결정 (summary_table에서 None 아닌 값이 하나라도 있는 항목만)
    if summary_table:
        shown_items = [
            item for item in AGENT_ITEMS
            if any(
                (sections.get("agent") or {}).get(_AGENT_ITEM_TO_KEY[item]) is not None
                for sections in summary_table.values()
            )
        ]
    else:
        non_zero = [
            item for item in AGENT_ITEMS
            if any(
                (data.get("agent_scores") or {}).get(item, 0.0) != 0.0
                for data in model_stats.values()
                if data.get("has_agent")
            )
        ]
        shown_items = non_zero or list(AGENT_ITEMS)

    if not shown_items:
        return None

    # z값과 텍스트 배열 구성
    z_values: list[list[float]] = []
    text_values: list[list[str]] = []

    for model in models:
        z_row: list[float] = []
        text_row: list[str] = []
        for item in shown_items:
            # summary_table에서 원본 None 여부 확인
            if summary_table and model in summary_table:
                raw = (summary_table[model].get("agent") or {}).get(
                    _AGENT_ITEM_TO_KEY[item]
                )
            else:
                raw = (model_stats[model].get("agent_scores") or {}).get(item)

            if raw is None:
                z_row.append(0.5)
                text_row.append("—")
            elif float(raw) >= 0.5:
                z_row.append(1.0)
                text_row.append("✅ 성공")
            else:
                z_row.append(0.0)
                text_row.append("❌ 실패")

        z_values.append(z_row)
        text_values.append(text_row)

    display_models = [MODEL_DISPLAY_NAMES.get(m, m) for m in models]
    display_items  = [AGENT_LABELS[k] for k in shown_items]

    fig = go.Figure(go.Heatmap(
        z=z_values,
        x=display_items,
        y=display_models,
        text=text_values,
        texttemplate="%{text}",
        colorscale=[[0, "#EF4444"], [0.5, "#D1D5DB"], [1, "#22C55E"]],
        showscale=False,
        zmin=0,
        zmax=1,
    ))
    fig.update_layout(
        height=max(200, 80 * len(models)),
        margin=dict(l=100, r=20, t=20, b=40),
        font=dict(size=12),
    )
    return fig


def build_positioning_matrix_fig(
    model_stats: dict[str, dict],
    eval_result: dict | None = None,
) -> go.Figure:
    """모델 포지셔닝 매트릭스 (2×2 사분면 버블 차트).

    x축: Knowledge 총점 (0~25)
    y축: Agent call_score × 100 (0~100%)
    버블 크기: 점수합 / 비용 (비용 효율). 비용 데이터 없으면 고정 크기.
    Agent 데이터 없으면 y=50 고정 점 차트로 폴백.
    """
    # 비용 데이터
    cost_dict: dict = (eval_result or {}).get("estimated_cost") or {}

    # 사분면 배경색 (shapes)
    shapes = [
        # 좌하: 개선 필요 (빨강)
        dict(type="rect", xref="x", yref="y",
             x0=0, y0=-10, x1=12.5, y1=50,
             fillcolor="#FEE2E2", opacity=0.6, line_width=0),
        # 우하: Knowledge 특화 (파랑)
        dict(type="rect", xref="x", yref="y",
             x0=12.5, y0=-10, x1=25, y1=50,
             fillcolor="#DBEAFE", opacity=0.6, line_width=0),
        # 좌상: Agent 특화 (노랑)
        dict(type="rect", xref="x", yref="y",
             x0=0, y0=50, x1=12.5, y1=110,
             fillcolor="#FEF3C7", opacity=0.6, line_width=0),
        # 우상: 최적 모델 (초록)
        dict(type="rect", xref="x", yref="y",
             x0=12.5, y0=50, x1=25, y1=110,
             fillcolor="#D1FAE5", opacity=0.6, line_width=0),
        # 중앙 수직선 (x=12.5)
        dict(type="line", xref="x", yref="y",
             x0=12.5, y0=-10, x1=12.5, y1=110,
             line=dict(color="#9CA3AF", width=1.2, dash="dot")),
        # 중앙 수평선 (y=50)
        dict(type="line", xref="x", yref="y",
             x0=0, y0=50, x1=25, y1=50,
             line=dict(color="#9CA3AF", width=1.2, dash="dot")),
    ]

    # 사분면 레이블 (annotations)
    quadrant_annotations = [
        dict(x=24.5, y=115, text="◆ 최적 모델",   showarrow=False,
             font=dict(size=10, color="#065F46"), xanchor="right"),
        dict(x=24.5, y=-10, text="▶ 지식 특화",   showarrow=False,
             font=dict(size=10, color="#1E40AF"), xanchor="right"),
        dict(x=0.5,  y=115, text="▶ Agent 특화",  showarrow=False,
             font=dict(size=10, color="#92400E"), xanchor="left"),
        dict(x=0.5,  y=-10, text="▼ 개선 필요",   showarrow=False,
             font=dict(size=10, color="#991B1B"), xanchor="left"),
    ]

    fig = go.Figure()

    has_any_a = any(d.get("has_agent") for d in model_stats.values())
    model_annotations = list(quadrant_annotations)

    # 좌표 중복 시 jitter용 카운터
    _coord_seen: dict[tuple, int] = {}

    for i, (model, data) in enumerate(model_stats.items()):
        color = MODEL_COLORS[i % len(MODEL_COLORS)]
        display = MODEL_DISPLAY_NAMES.get(model, model)

        x_val = float(data["knowledge_total"] or 0.0) if data.get("has_knowledge") else 0.0

        if has_any_a and data.get("has_agent"):
            raw_call = data["agent_scores"].get("call") or 0.0
            y_val = round(float(raw_call) * 100, 1)
        else:
            y_val = 50.0  # Agent 없으면 중앙 고정

        # 좌표 중복 시 소량 jitter 적용 (0.4pt / 2%)
        coord_key = (round(x_val, 1), round(y_val, 1))
        jitter_n = _coord_seen.get(coord_key, 0)
        if jitter_n > 0:
            x_val += jitter_n * 0.4
            y_val += jitter_n * 2.0
        _coord_seen[coord_key] = jitter_n + 1

        print(
            f"[positioning_matrix] model={model!r} x={x_val:.2f} y={y_val:.2f} "
            f"has_k={data.get('has_knowledge')} has_a={data.get('has_agent')}"
        )

        fig.add_trace(go.Scatter(
            x=[x_val],
            y=[y_val],
            mode="markers",
            name=display,
            marker=dict(
                size=22,
                color=color,
                opacity=0.9,
                line=dict(width=2, color="white"),
            ),
        ))

        # 모델명 레이블: 마커 위에 annotation으로 표시
        model_annotations.append(dict(
            x=x_val, y=y_val,
            text=f"<b>{display}</b>",
            showarrow=True,
            arrowhead=0,
            arrowcolor=color,
            arrowwidth=1.5,
            ax=0, ay=-28,
            font=dict(size=11, color=color),
            bgcolor="white",
            bordercolor=color,
            borderwidth=1,
            borderpad=3,
        ))

    fig.update_layout(
        title=dict(text="모델 포지셔닝 매트릭스", font=dict(size=13), x=0.5, xanchor="center"),
        xaxis=dict(title="Knowledge 총점 (/25점)", range=[-1, 27], showgrid=False),
        yaxis=dict(title="Agent Tool 호출 성공률 (%)", range=[-20, 130], showgrid=False),
        shapes=shapes,
        annotations=model_annotations,
        height=500,
        plot_bgcolor="white",
        margin=dict(l=80, r=160, t=80, b=80),
        font=dict(size=11),
        legend=dict(orientation="h", yanchor="bottom", y=1.08, xanchor="right", x=1),
        showlegend=True,
    )
    return fig


def build_agent_table_fig(
    model_stats: dict[str, dict],
    summary_table: dict | None = None,
) -> go.Figure | None:
    """Agent 항목별 성공/실패 go.Table.

    셀 값:
      1      → 배경 #D1FAE5, 글자 #065F46, "● 성공"
      0      → 배경 #FEE2E2, 글자 #991B1B, "● 실패"
      None   → 배경 #F3F4F6, 글자 #6B7280, "—"

    summary_table에서 None인 열 전체 제거.
    데이터 없으면 None 반환.
    """
    models = [m for m, d in model_stats.items() if d.get("has_agent")]
    if not models:
        return None

    if summary_table:
        shown_items = [
            item for item in AGENT_ITEMS
            if any(
                (sections.get("agent") or {}).get(_AGENT_ITEM_TO_KEY[item]) is not None
                for sections in summary_table.values()
            )
        ]
    else:
        non_zero = [
            item for item in AGENT_ITEMS
            if any(
                (data.get("agent_scores") or {}).get(item, 0.0) != 0.0
                for data in model_stats.values()
                if data.get("has_agent")
            )
        ]
        shown_items = non_zero or list(AGENT_ITEMS)

    if not shown_items:
        return None

    # 짧은 헤더 레이블
    _SHORT_LABELS = {
        "call":       "Tool 호출",
        "slot":       "슬롯 요청",
        "relevance":  "거절 적절성",
        "completion": "결과 전달",
    }

    # go.Table은 열 기준 데이터 구조 — 각 열마다 값/색상 배열
    header_labels = ["모델"] + [_SHORT_LABELS.get(k, k) for k in shown_items]

    # 모델명 열
    col_model_vals   = [MODEL_DISPLAY_NAMES.get(m, m) for m in models]
    col_model_fill   = ["#F9FAFB"] * len(models)
    col_model_font   = ["#111827"] * len(models)

    # 항목별 열 구성
    item_cols_vals:  list[list[str]]  = []
    item_cols_fill:  list[list[str]]  = []
    item_cols_font:  list[list[str]]  = []

    for item in shown_items:
        vals_col:  list[str] = []
        fill_col:  list[str] = []
        font_col:  list[str] = []
        for model in models:
            if summary_table and model in summary_table:
                raw = (summary_table[model].get("agent") or {}).get(_AGENT_ITEM_TO_KEY[item])
            else:
                raw = (model_stats[model].get("agent_scores") or {}).get(item)

            if raw is None:
                vals_col.append("—")
                fill_col.append("#F3F4F6")
                font_col.append("#6B7280")
            elif float(raw) == 0:
                vals_col.append("✗ 실패")
                fill_col.append("#FEE2E2")
                font_col.append("#991B1B")
            elif float(raw) > 1:
                # 1~3 범위 Judge 점수 (completion) — 숫자 그대로 표시
                vals_col.append(str(int(float(raw))))
                fill_col.append("#D1FAE5")
                font_col.append("#065F46")
            else:
                vals_col.append("● 성공")
                fill_col.append("#D1FAE5")
                font_col.append("#065F46")

        item_cols_vals.append(vals_col)
        item_cols_fill.append(fill_col)
        item_cols_font.append(font_col)

    # go.Table은 column-oriented: values는 [각 셀] per column
    all_vals  = [col_model_vals]  + item_cols_vals
    all_fills = [col_model_fill]  + item_cols_fill
    all_fonts = [col_model_font]  + item_cols_font

    fig = go.Figure(go.Table(
        header=dict(
            values=header_labels,
            fill_color="#1E3A5F",
            font=dict(color="white", size=12),
            align="center",
            height=32,
        ),
        cells=dict(
            values=all_vals,
            fill_color=all_fills,
            font=dict(color=all_fonts, size=12),
            align="center",
            height=30,
        ),
    ))
    fig.update_layout(
        height=150 + 30 * len(models),
        margin=dict(l=0, r=0, t=0, b=0),
    )
    return fig


def build_combined_bar_fig(model_stats: dict[str, dict]) -> go.Figure | None:
    """모델별 Knowledge 총점(×4 환산, 100점 만점) + Agent 성공률(%) 그룹 바 차트.

    Knowledge가 없는 모델은 Knowledge 바 생략, Agent가 없는 모델은 Agent 바 생략.
    둘 다 없으면 None 반환.
    """
    models = list(model_stats.keys())
    if not models:
        return None

    has_any_k = any(d.get("has_knowledge") for d in model_stats.values())
    has_any_a = any(d.get("has_agent") for d in model_stats.values())
    if not has_any_k and not has_any_a:
        return None

    display_models = [MODEL_DISPLAY_NAMES.get(m, m) for m in models]
    fig = go.Figure()

    if has_any_k:
        k_vals = [
            round(model_stats[m]["knowledge_total"] * 4, 1) if model_stats[m].get("has_knowledge") else None
            for m in models
        ]
        fig.add_trace(go.Bar(
            name="Knowledge 점수",
            x=display_models,
            y=k_vals,
            marker_color="#4F8EF7",
            text=[f"{v:.1f}" if v is not None else "" for v in k_vals],
            textposition="outside",
        ))

    if has_any_a:
        a_vals = [
            round(model_stats[m]["agent_scores"].get("call", 0.0) * 100, 1) if model_stats[m].get("has_agent") else None
            for m in models
        ]
        fig.add_trace(go.Bar(
            name="Agent 성공률",
            x=display_models,
            y=a_vals,
            marker_color="#22C55E",
            text=[f"{v:.1f}" if v is not None else "" for v in a_vals],
            textposition="outside",
        ))

    fig.update_layout(
        barmode="group",
        yaxis=dict(title="점수 / 성공률 (%)", range=[0, 115]),
        height=420,
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
