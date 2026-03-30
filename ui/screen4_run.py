"""
BenchMate — Screen 4: 모델 선택 + 파이프라인 실행
"""

import streamlit as st

from pipeline.graph import build_graph
from pipeline.nodes._hf_error import JudgeError

# ── 모델 메타데이터 ────────────────────────────────────────────────────────────

_MODELS = [
    {"key": "solar-pro",     "label": "Solar Pro",     "provider": "Upstage"},
    {"key": "gpt-4o",        "label": "GPT-4o",        "provider": "OpenAI"},
    {"key": "claude-sonnet", "label": "Claude Sonnet", "provider": "Anthropic"},
]

_MODEL_BY_KEY: dict[str, dict] = {m["key"]: m for m in _MODELS}

# ── 노드명 → 한국어 진행 메시지 ────────────────────────────────────────────────

_NODE_LABELS: dict[str, str] = {
    "load_scenarios":      "문항 로딩 중...",
    "route_mode":          "평가 모드 확인 중...",
    "generate_responses":  "모델 응답 수집 중...",
    "generate_tool_calls": "모델 Tool 호출 수집 중...",
    "judge_knowledge":     "채점 중 (지식 평가)...",
    "evaluate_call":       "Tool 호출 정확도 채점 중...",
    "judge_agent":         "채점 중 (업무 자동화 평가)...",
    "validate_scores":     "채점 결과 검증 중...",
    "flag_human_review":   "Human Review 큐 구성 중...",
    "aggregate_results":   "결과 집계 중...",
    "generate_report":     "리포트 생성 중...",
}


# ── 모델 선택 UI ───────────────────────────────────────────────────────────────

def _render_model_selector() -> None:
    st.subheader("비교할 모델을 선택하세요")
    st.caption("최소 1개 이상 선택하세요.")

    model_keys = [m["key"] for m in _MODELS]
    model_labels = {m["key"]: f"{m['label']} ({m['provider']})" for m in _MODELS}

    current = st.session_state.get("selected_models", [])

    selected = st.multiselect(
        "평가 모델",
        options=model_keys,
        default=[k for k in current if k in model_keys],
        format_func=lambda k: model_labels[k],
        label_visibility="collapsed",
    )

    st.session_state["selected_models"] = selected


def _render_selected_cards() -> None:
    selected_keys: list[str] = st.session_state.get("selected_models", [])
    if not selected_keys:
        return

    st.markdown("#### 선택된 모델")

    cols = st.columns(len(selected_keys))
    for col, key in zip(cols, selected_keys):
        model = _MODEL_BY_KEY[key]
        with col:
            st.markdown(
                f"""
                <div style="
                    border: 1.5px solid #4F8EF7;
                    border-radius: 10px;
                    padding: 1rem 1.2rem;
                    background: #f5f8ff;
                    text-align: center;
                ">
                    <div style="font-weight: 700; font-size: 1rem; color: #1a1a2e;">{model['label']}</div>
                    <div style="font-size: 0.8rem; color: #666; margin-top: 4px;">{model['provider']}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


# ── 파이프라인 실행 ────────────────────────────────────────────────────────────

def _build_initial_state() -> dict:
    state: dict = {
        "eval_mode":       st.session_state.get("eval_mode", "knowledge"),
        "domain":          st.session_state.get("domain", "finance"),
        "selected_models": st.session_state.get("selected_models", []),
    }

    for key in ("questions", "scenarios", "available_tools"):
        value = st.session_state.get(key)
        if value is not None:
            state[key] = value

    return state


def _run_pipeline() -> None:
    try:
        graph = build_graph()
        initial_state = _build_initial_state()

        selected_models: list[str] = initial_state["selected_models"]
        model_labels = [
            _MODEL_BY_KEY[k]["label"] for k in selected_models if k in _MODEL_BY_KEY
        ]

        with st.spinner("파이프라인 실행 중..."):
            with st.status("평가를 진행하고 있습니다.", expanded=True) as status:
                node_outputs: dict = {}

                for step in graph.stream(initial_state):  # type: ignore[arg-type]
                    node_name = next(iter(step))
                    node_output = step[node_name]

                    node_outputs[node_name] = node_output

                    label = _NODE_LABELS.get(node_name, f"{node_name} 처리 중...")

                    if node_name in ("generate_responses", "generate_tool_calls") and model_labels:
                        label = f"{', '.join(model_labels)} 응답 수집 중..."

                    st.write(f"✓ {label}")

                status.update(label="평가 완료!", state="complete", expanded=False)

        merged: dict = dict(initial_state)
        for node_output in node_outputs.values():
            if isinstance(node_output, dict):
                merged.update(node_output)

        st.session_state["eval_result"] = merged
        st.session_state["current_screen"] = 5
        st.rerun()

    except JudgeError as exc:
        st.warning(
            f"채점 모델 연결에 문제가 발생했습니다.\n\n"
            f"**원인:** {exc}\n\n"
            "모델 응답 수집은 완료됐으니 크레딧 충전 후 다시 시도하시면 됩니다."
        )
    except Exception as exc:
        st.warning(f"평가 실행 중 오류가 발생했습니다: {exc}")


# ── render ─────────────────────────────────────────────────────────────────────

def render() -> None:
    st.title("BenchMate")
    st.write("평가할 모델을 선택하고 파이프라인을 실행하세요.")
    st.divider()

    _render_model_selector()

    selected_keys: list[str] = st.session_state.get("selected_models", [])

    if selected_keys:
        st.divider()
        _render_selected_cards()

    st.divider()

    can_run = len(selected_keys) > 0

    if not can_run:
        st.caption("모델을 1개 이상 선택하면 평가를 시작할 수 있습니다.")

    if st.button(
        "평가 시작",
        disabled=not can_run,
        type="primary",
        use_container_width=True,
    ):
        _run_pipeline()

    st.divider()

    col_prev, col_next = st.columns(2)
    with col_prev:
        if st.button("← 이전", use_container_width=True):
            st.session_state["current_screen"] = 3
            st.rerun()
    with col_next:
        eval_result = st.session_state.get("eval_result")
        if st.button(
            "다음 →",
            disabled=eval_result is None,
            use_container_width=True,
        ):
            st.session_state["current_screen"] = 5
            st.rerun()
