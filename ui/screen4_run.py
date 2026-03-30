"""
BenchMate — Screen 4: 모델 선택 + 파이프라인 실행
"""

import streamlit as st

from pipeline.graph import build_graph

# ── 모델 메타데이터 ────────────────────────────────────────────────────────────

_MODELS = [
    {"key": "solar-pro",     "label": "Solar Pro",     "provider": "Upstage",       "available": True},
    {"key": "gpt-4o",        "label": "GPT-4o",        "provider": "OpenAI",         "available": True},
    {"key": "claude-sonnet", "label": "Claude Sonnet", "provider": "Anthropic",      "available": True},
    {"key": "hyperclovax",   "label": "HyperCLOVA X",  "provider": "NAVER",          "available": False},
    {"key": "exaone",        "label": "EXAONE",        "provider": "LG AI Research", "available": False},
]

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
    st.caption("최소 1개 이상 선택하세요. '준비 중' 모델은 현재 평가에 포함되지 않습니다.")

    selected: list[str] = st.session_state.setdefault("selected_models", [])

    available_models = [m for m in _MODELS if m["available"]]
    unavailable_models = [m for m in _MODELS if not m["available"]]

    cols = st.columns(len(_MODELS))

    for i, model in enumerate(available_models):
        with cols[i]:
            checked = model["key"] in selected
            new_checked = st.checkbox(
                model["label"],
                value=checked,
                key=f"model_chk_{model['key']}",
            )
            if new_checked != checked:
                if new_checked:
                    selected.append(model["key"])
                else:
                    selected.remove(model["key"])
                st.session_state["selected_models"] = selected
                st.rerun()

    for i, model in enumerate(unavailable_models):
        col_idx = len(available_models) + i
        with cols[col_idx]:
            st.checkbox(
                model["label"],
                value=False,
                disabled=True,
                key=f"model_chk_{model['key']}",
            )
            st.caption("준비 중")


def _render_selected_cards() -> None:
    selected_keys: list[str] = st.session_state.get("selected_models", [])
    if not selected_keys:
        return

    selected_meta = [m for m in _MODELS if m["key"] in selected_keys]
    st.markdown("#### 선택된 모델")

    cols = st.columns(len(selected_meta))
    for col, model in zip(cols, selected_meta):
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
    return {
        "eval_mode":       st.session_state.get("eval_mode", "knowledge"),
        "domain":          st.session_state.get("domain", "finance"),
        "selected_models": st.session_state.get("selected_models", []),
    }


def _run_pipeline() -> None:
    graph = build_graph()
    initial_state = _build_initial_state()

    selected_models: list[str] = initial_state["selected_models"]
    model_labels = [
        m["label"] for m in _MODELS if m["key"] in selected_models
    ]

    with st.spinner("파이프라인 실행 중..."):
        with st.status("평가를 진행하고 있습니다.", expanded=True) as status:
            final_state: dict = {}

            for step in graph.stream(initial_state):  # type: ignore[arg-type]
                node_name = next(iter(step))
                node_output = step[node_name]

                if node_name in final_state:
                    final_state[node_name].update(node_output)
                else:
                    final_state[node_name] = node_output

                label = _NODE_LABELS.get(node_name, f"{node_name} 처리 중...")

                # 응답 수집 단계: 선택 모델 이름도 함께 표시
                if node_name in ("generate_responses", "generate_tool_calls") and model_labels:
                    models_str = ", ".join(model_labels)
                    label = f"{models_str} 응답 수집 중..."

                st.write(f"✓ {label}")

            status.update(label="평가 완료!", state="complete", expanded=False)

    # 최종 집계 state 복원 (stream은 노드별 출력만 반환하므로 병합)
    merged: dict = dict(initial_state)
    for node_output in final_state.values():
        if isinstance(node_output, dict):
            merged.update(node_output)

    st.session_state["eval_result"] = merged
    st.session_state["current_screen"] = 5
    st.rerun()


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
