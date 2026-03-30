import json
import os
from typing import Any

import pandas as pd
import streamlit as st

_TOOLS_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "tools")

_DOMAIN_TOOL_FILE: dict[str, str] = {
    "finance": "finance_tools.json",
    "legal": "legal_tools.json",
    "hr": "hr_tools.json",
    "cs": "cs_tools.json",
    "manufacturing": "manufacturing_tools.json",
}

_DIFFICULTY_OPTIONS = ["easy", "medium", "hard"]
_TASK_TYPE_OPTIONS = ["explanation", "calculation", "summary", "translation", "comparison"]
_SCENARIO_TYPE_OPTIONS = ["single_A", "single_B", "single_C"]
_SCENARIO_TYPE_LABELS = {
    "single_A": "유형 A: 단일 기능 호출 (정답 기능 있음)",
    "single_B": "유형 B: 기능 불필요 (직접 답변)",
    "single_C": "유형 C: 불가능 요청 (거절 필요)",
}

_KNOWLEDGE_SELECTBOX_DEFAULTS = {
    "difficulty_index": _DIFFICULTY_OPTIONS.index("hard"),
    "task_type_index": _TASK_TYPE_OPTIONS.index("calculation"),
}

_KNOWLEDGE_PLACEHOLDERS = {
    "question": "예: DSR 40% 규제 적용 시, 연소득 6,000만원인 차주의 월 최대 원리금 상환 가능액은 얼마인가?",
    "answer": "예: DSR 40% 기준으로 연소득 6,000만원의 40%인 2,400만원이 연간 상환 가능액이며, 월 기준으로는 200만원이 상한선이다.",
    "rubric": "예: 2,400만원(연간) 또는 200만원(월) 계산이 정확한가? DSR 40% × 연소득 공식을 사용했는가?",
}

_AGENT_REQUEST_PLACEHOLDERS: dict[str, str] = {
    "single_A": "예: 홍길동 고객(ID: C-1234)의 신용점수가 720점인데 현재 적용 가능한 대출 금리 조회해줘.",
    "single_B": "예: 이 고객 대출 금리 조회해줘.",
    "single_C": "예: KB국민은행 내부 대출 금리 데이터 조회해줘.",
}

# tool 이름 → {파라미터명: 예시값}  (number_input의 help=, text_input의 placeholder= 에 사용)
_AGENT_PARAM_EXAMPLES: dict[str, dict[str, Any]] = {
    "search_loan_rate": {
        "customer_id": "C-1234",
        "credit_score": 720,
    },
}


def _load_tools(domain: str) -> list[dict]:
    filename = _DOMAIN_TOOL_FILE.get(domain, "")
    if not filename:
        return []
    path = os.path.join(_TOOLS_DIR, filename)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("tools", [])


def _render_knowledge_form() -> None:
    st.subheader("도메인 지식 평가 — 문항 등록")

    questions: list[dict[str, Any]] = st.session_state.setdefault("questions", [])

    with st.form("knowledge_question_form", clear_on_submit=True):
        st.markdown("#### 새 문항 추가")
        question_text = st.text_area(
            "질문 *",
            placeholder=_KNOWLEDGE_PLACEHOLDERS["question"],
            height=100,
        )
        answer_text = st.text_area(
            "정답 *",
            placeholder=_KNOWLEDGE_PLACEHOLDERS["answer"],
            height=100,
        )
        rubric_text = st.text_area(
            "핵심 채점 포인트",
            placeholder=_KNOWLEDGE_PLACEHOLDERS["rubric"],
            height=80,
            help="AI 채점 모델이 이 포인트를 기준으로 채점합니다. 비워두면 정답 기반 일반 채점이 적용됩니다.",
        )
        col_diff, col_type = st.columns(2)
        with col_diff:
            difficulty = st.selectbox(
                "난이도", _DIFFICULTY_OPTIONS, index=_KNOWLEDGE_SELECTBOX_DEFAULTS["difficulty_index"]
            )
        with col_type:
            task_type = st.selectbox(
                "태스크 유형", _TASK_TYPE_OPTIONS, index=_KNOWLEDGE_SELECTBOX_DEFAULTS["task_type_index"]
            )

        submitted = st.form_submit_button("문항 추가 +", type="primary", use_container_width=True)

    if submitted:
        if not question_text.strip():
            st.error("질문을 입력하세요.")
        elif not answer_text.strip():
            st.error("정답을 입력하세요.")
        else:
            questions.append(
                {
                    "id": len(questions) + 1,
                    "question": question_text.strip(),
                    "answer": answer_text.strip(),
                    "instance_rubric": rubric_text.strip(),
                    "difficulty": difficulty,
                    "task_type": task_type,
                }
            )
            st.session_state["questions"] = questions
            st.success(f"문항 {len(questions)}개 등록됨")
            st.rerun()

    if questions:
        st.divider()
        st.markdown(f"#### 등록된 문항 목록 ({len(questions)}개)")
        df = pd.DataFrame(
            [
                {
                    "#": q["id"],
                    "질문 (요약)": q["question"][:60] + ("…" if len(q["question"]) > 60 else ""),
                    "난이도": q["difficulty"],
                    "유형": q["task_type"],
                    "채점 포인트": "✓" if q["instance_rubric"] else "—",
                }
                for q in questions
            ]
        )
        st.dataframe(df, use_container_width=True, hide_index=True)

        if st.button("전체 초기화", key="clear_questions"):
            st.session_state["questions"] = []
            st.rerun()
    else:
        st.info("아직 등록된 문항이 없습니다. 위 폼으로 문항을 추가하세요.")


def _render_param_fields(
    params: list[dict],
    examples: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """파라미터 배열을 받아 type별 입력 위젯을 렌더링하고 {name: value} dict를 반환한다.
    st.form 내부에서 호출되어야 한다."""
    if examples is None:
        examples = {}
    values: dict[str, Any] = {}
    for p in params:
        name: str = p["name"]
        ptype: str = p["type"]
        desc: str = p.get("description", "")
        required: bool = p.get("required", False)
        label = f"{name}{' *' if required else ''}"
        key = f"param_{name}"

        if desc:
            st.caption(desc)

        if ptype == "integer":
            example = examples.get(name)
            help_text = f"예시: {example}" if example is not None else None
            values[name] = st.number_input(label, step=1, value=0, help=help_text, key=key)
        elif ptype == "float":
            example = examples.get(name)
            help_text = f"예시: {example}" if example is not None else None
            values[name] = st.number_input(
                label, step=0.1, value=0.0, format="%.2f", help=help_text, key=key
            )
        else:  # string (기본)
            example = examples.get(name)
            placeholder = f"예시: {example}" if example is not None else ""
            values[name] = st.text_input(label, placeholder=placeholder, key=key)

    return values


def _render_agent_form() -> None:
    st.subheader("업무 자동화 능력 평가 — 시나리오 등록")

    domain: str | None = st.session_state.get("domain")
    tools = _load_tools(domain) if domain else []
    tool_names = [t["name"] for t in tools]

    scenarios: list[dict[str, Any]] = st.session_state.setdefault("scenarios", [])

    st.markdown("#### 새 시나리오 추가")

    # ── form 밖: 선택 변경 시 즉시 rerun이 필요한 selectbox ──────────────────
    scenario_type: str = st.selectbox(
        "시나리오 유형",
        options=_SCENARIO_TYPE_OPTIONS,
        format_func=lambda k: _SCENARIO_TYPE_LABELS[k],
        key="agent_scenario_type",
    )

    correct_tool: str = ""
    selected_tool_params: list[dict] = []

    if scenario_type == "single_A":
        st.markdown("---")
        st.markdown("**유형 A 설정 — 정답 기능 및 입력값**")
        if tool_names:
            default_tool_idx = tool_names.index("search_loan_rate") if "search_loan_rate" in tool_names else 0
            correct_tool = st.selectbox(
                "정답 기능 *",
                options=tool_names,
                index=default_tool_idx,
                key="agent_correct_tool",
            )
            selected_tool_meta = next((t for t in tools if t["name"] == correct_tool), None)
            if selected_tool_meta:
                selected_tool_params = selected_tool_meta.get("parameters", [])
        else:
            st.warning("선택된 도메인에 등록된 기능이 없습니다. 이전 화면에서 도메인을 확인하세요.")
            correct_tool = st.text_input("정답 기능 이름 (직접 입력)", key="agent_correct_tool_manual")

    # ── form 안: 나머지 입력 필드 + 제출 버튼 ────────────────────────────────
    request_placeholder = _AGENT_REQUEST_PLACEHOLDERS.get(scenario_type, "")
    with st.form("agent_scenario_form", clear_on_submit=True):
        user_request = st.text_area(
            "사용자 요청 *",
            placeholder=request_placeholder,
            height=100,
            key="agent_user_request",
        )

        param_values: dict[str, Any] = {}
        if scenario_type == "single_A" and selected_tool_params:
            st.markdown("**기대 파라미터**")
            param_examples = _AGENT_PARAM_EXAMPLES.get(correct_tool, {})
            param_values = _render_param_fields(selected_tool_params, examples=param_examples)

        submitted = st.form_submit_button("시나리오 추가 +", type="primary", use_container_width=True)

    if submitted:
        if not user_request.strip():
            st.error("사용자 요청을 입력하세요.")
        elif scenario_type == "single_A" and not correct_tool:
            st.error("유형 A 시나리오에는 정답 기능을 선택하세요.")
        else:
            # 필수 파라미터 누락 검사
            missing = [
                p["name"]
                for p in selected_tool_params
                if p.get("required") and str(param_values.get(p["name"], "")).strip() == ""
                and p["type"] == "string"
            ]
            if missing:
                st.error(f"필수 파라미터를 입력하세요: {', '.join(missing)}")
            else:
                scenarios.append(
                    {
                        "id": len(scenarios) + 1,
                        "scenario_type": scenario_type,
                        "user_request": user_request.strip(),
                        "correct_tool": correct_tool if scenario_type == "single_A" else None,
                        "expected_params": param_values if scenario_type == "single_A" else {},
                    }
                )
                st.session_state["scenarios"] = scenarios
                st.success(f"시나리오 {len(scenarios)}개 등록됨")
                st.rerun()

    if scenarios:
        st.divider()
        st.markdown(f"#### 등록된 시나리오 목록 ({len(scenarios)}개)")
        df = pd.DataFrame(
            [
                {
                    "#": s["id"],
                    "유형": s["scenario_type"],
                    "요청 (요약)": s["user_request"][:60] + ("…" if len(s["user_request"]) > 60 else ""),
                    "정답 기능": s["correct_tool"] or "—",
                }
                for s in scenarios
            ]
        )
        st.dataframe(df, use_container_width=True, hide_index=True)

        if st.button("전체 초기화", key="clear_scenarios"):
            st.session_state["scenarios"] = []
            st.rerun()
    else:
        st.info("아직 등록된 시나리오가 없습니다. 위 폼으로 시나리오를 추가하세요.")


def render() -> None:
    st.title("BenchMate")

    eval_mode: str = st.session_state.get("eval_mode", "knowledge")

    mode_labels = {
        "knowledge": "도메인 지식 평가",
        "agent": "업무 자동화 능력 평가",
        "integrated": "종합 평가",
    }
    st.write(f"평가 시나리오를 구성하세요.  **모드: {mode_labels.get(eval_mode, eval_mode)}**")
    st.divider()

    if eval_mode == "knowledge":
        _render_knowledge_form()

    elif eval_mode == "agent":
        _render_agent_form()

    else:  # integrated
        tab_k, tab_a = st.tabs(["도메인 지식 평가", "업무 자동화 능력 평가"])
        with tab_k:
            _render_knowledge_form()
        with tab_a:
            _render_agent_form()

    st.divider()

    questions: list = st.session_state.get("questions", [])
    scenarios: list = st.session_state.get("scenarios", [])

    # 다음 버튼 활성화 조건 확인
    can_proceed = False
    if eval_mode == "knowledge" and questions:
        can_proceed = True
    elif eval_mode == "agent" and scenarios:
        can_proceed = True
    elif eval_mode == "integrated" and questions and scenarios:
        can_proceed = True

    if not can_proceed:
        if eval_mode == "knowledge":
            st.caption("문항을 1개 이상 등록하면 다음으로 이동할 수 있습니다.")
        elif eval_mode == "agent":
            st.caption("시나리오를 1개 이상 등록하면 다음으로 이동할 수 있습니다.")
        else:
            st.caption("도메인 지식 평가 문항과 업무 자동화 능력 평가 시나리오를 각각 1개 이상 등록하면 다음으로 이동할 수 있습니다.")

    col_prev, col_next = st.columns(2)
    with col_prev:
        if st.button("← 이전", use_container_width=True):
            st.session_state["current_screen"] = 2
            st.rerun()
    with col_next:
        if st.button(
            "다음 →",
            disabled=not can_proceed,
            type="primary",
            use_container_width=True,
        ):
            st.session_state["current_screen"] = 4
            st.rerun()
