"""
BenchMate — Screen 6: Human Review
담당자가 Judge 채점 결과를 검토·수정하는 인터페이스.
"""

from __future__ import annotations

import streamlit as st

# ── 상수 ──────────────────────────────────────────────────────────────────────

_KNOWLEDGE_FIELDS: list[tuple[str, str]] = [
    ("accuracy",         "사실 정확도"),
    ("fluency",          "한국어 자연성"),
    ("hallucination",    "허위 정보 없음"),
    ("domain_expertise", "도메인 전문성"),
    ("utility",          "응답 적절성"),
]


# ── judge_reliability 계산 ────────────────────────────────────────────────────

def _calc_judge_reliability(queue: list[dict]) -> float:
    """
    Human Review가 완료된 항목들에 대해 Judge-Human 일치율(%)을 계산한다.
    Knowledge: 5개 항목 각각 일치 여부를 비교.
    Agent: call_score 일치 여부를 비교.
    """
    total = 0
    matched = 0

    for item in queue:
        if not item.get("is_reviewed"):
            continue
        human_score: dict | None = item.get("human_score")
        judge_score: dict = item.get("judge_score", {})
        if not human_score:
            continue

        if item.get("item_type") == "knowledge":
            for key, _ in _KNOWLEDGE_FIELDS:
                human_val = human_score.get(key)
                judge_val = judge_score.get(key)
                if human_val is not None and judge_val is not None:
                    total += 1
                    if human_val == judge_val:
                        matched += 1
        else:  # agent
            human_call = human_score.get("call_score")
            judge_call = judge_score.get("call_score")
            if human_call is not None and judge_call is not None:
                total += 1
                if human_call == judge_call:
                    matched += 1

    if total == 0:
        return 100.0
    return (matched / total) * 100.0


# ── 빈 상태 화면 ──────────────────────────────────────────────────────────────

def _render_empty_state() -> None:
    st.info("검토할 항목이 없습니다.")
    col_prev, _, col_next = st.columns([1, 2, 1])
    with col_prev:
        if st.button("← 이전 (결과 대시보드)", use_container_width=True):
            st.session_state["current_screen"] = 5
            st.rerun()
    with col_next:
        if st.button("다음 (PM 리포트) →", type="primary", use_container_width=True):
            st.session_state["current_screen"] = 7
            st.rerun()


# ── Knowledge 항목 폼 ─────────────────────────────────────────────────────────

def _render_knowledge_form(idx: int, item: dict) -> dict | None:
    """
    Knowledge 항목의 수정 폼을 렌더링한다.
    '검토 완료' 클릭 시 HumanScoreDetail dict 반환, 아니면 None.
    """
    judge_score: dict = item.get("judge_score", {})

    st.markdown("**Judge 채점 결과**")

    cols = st.columns(len(_KNOWLEDGE_FIELDS))
    for col, (key, label) in zip(cols, _KNOWLEDGE_FIELDS):
        with col:
            st.metric(label=label, value=judge_score.get(key, "—"))

    reason = judge_score.get("reason", "")
    if reason:
        st.caption(f"Judge 채점 이유: {reason}")

    st.markdown("**담당자 수정 점수**")
    new_scores: dict[str, int] = {}
    slider_cols = st.columns(len(_KNOWLEDGE_FIELDS))
    for col, (key, label) in zip(slider_cols, _KNOWLEDGE_FIELDS):
        with col:
            default_val = int(judge_score.get(key) or 3)
            new_scores[key] = st.slider(
                label=label,
                min_value=1,
                max_value=5,
                value=default_val,
                key=f"s6_slider_{idx}_{key}",
            )

    if st.button("검토 완료", key=f"s6_submit_{idx}", type="primary"):
        return {
            "accuracy":         new_scores["accuracy"],
            "fluency":          new_scores["fluency"],
            "hallucination":    new_scores["hallucination"],
            "domain_expertise": new_scores["domain_expertise"],
            "utility":          new_scores["utility"],
            "call_score":       None,
        }
    return None


# ── Agent 항목 폼 ─────────────────────────────────────────────────────────────

def _render_agent_form(idx: int, item: dict) -> dict | None:
    """
    Agent 항목의 수정 폼을 렌더링한다.
    '검토 완료' 클릭 시 HumanScoreDetail dict 반환, 아니면 None.
    """
    judge_score: dict = item.get("judge_score", {})
    judge_call = judge_score.get("call_score", "—")

    st.metric(label="Judge call_score", value=str(judge_call))

    reason = judge_score.get("reason", "")
    if reason:
        st.caption(f"채점 이유: {reason}")

    default_idx = 0 if judge_call != 1 else 1
    human_call = st.radio(
        "담당자 수정 call_score",
        options=[0, 1],
        index=default_idx,
        horizontal=True,
        key=f"s6_radio_{idx}",
    )

    if st.button("검토 완료", key=f"s6_submit_{idx}", type="primary"):
        return {
            "accuracy":         None,
            "fluency":          None,
            "hallucination":    None,
            "domain_expertise": None,
            "utility":          None,
            "call_score":       human_call,
        }
    return None


# ── render ────────────────────────────────────────────────────────────────────

def render() -> None:
    st.title("BenchMate")
    st.write("Human Review — 채점 결과 검토 및 수정")
    st.divider()

    eval_result: dict | None = st.session_state.get("eval_result")
    queue: list[dict] = (eval_result or {}).get("human_review_queue") or []

    if not queue:
        _render_empty_state()
        return

    reviewed_count = sum(1 for item in queue if item.get("is_reviewed"))
    total_count = len(queue)
    st.caption(f"검토 진행: {reviewed_count} / {total_count}")
    st.progress(reviewed_count / total_count if total_count else 0)

    # ── 모든 항목 검토 완료 시 신뢰도 표시 ──────────────────────────────────
    if reviewed_count == total_count:
        reliability: float = eval_result.get("judge_reliability") or _calc_judge_reliability(queue)
        st.success(f"채점 신뢰도: {reliability:.1f}% 로 측정됐습니다.")

    st.divider()

    # ── 항목별 카드 ───────────────────────────────────────────────────────────
    for idx, item in enumerate(queue):
        item_id: str = item.get("item_id", f"item_{idx}")
        model_name: str = item.get("model_name", "unknown")
        item_type: str = item.get("item_type", "knowledge")
        review_reason: str = item.get("review_reason", "")
        is_reviewed: bool = item.get("is_reviewed", False)

        with st.expander(
            f"{'✅' if is_reviewed else '⬜'} [{idx + 1}] {item_id} — {model_name}",
            expanded=not is_reviewed,
        ):
            col_meta1, col_meta2, col_meta3 = st.columns(3)
            with col_meta1:
                st.markdown(f"**항목 ID** `{item_id}`")
            with col_meta2:
                st.markdown(f"**모델** `{model_name}`")
            with col_meta3:
                st.markdown(f"**등록 사유** {review_reason}")

            if is_reviewed:
                st.success("검토 완료")
                human_score = item.get("human_score") or {}
                if item_type == "knowledge":
                    score_cols = st.columns(len(_KNOWLEDGE_FIELDS))
                    for col, (key, label) in zip(score_cols, _KNOWLEDGE_FIELDS):
                        with col:
                            st.metric(label=label, value=human_score.get(key, "—"))
                else:
                    st.metric(label="수정 call_score", value=str(human_score.get("call_score", "—")))
            else:
                if item_type == "knowledge":
                    human_score_result = _render_knowledge_form(idx, item)
                else:
                    human_score_result = _render_agent_form(idx, item)

                if human_score_result is not None:
                    # 인플레이스 업데이트 (eval_result 내 queue 변경)
                    item["human_score"] = human_score_result
                    item["is_reviewed"] = True

                    # 마지막 항목이었으면 즉시 judge_reliability 계산·저장
                    all_done = all(q.get("is_reviewed") for q in queue)
                    if all_done and eval_result is not None:
                        eval_result["judge_reliability"] = _calc_judge_reliability(queue)

                    if eval_result is not None:
                        st.session_state["eval_result"] = eval_result
                    st.rerun()

    st.divider()

    # ── 하단 네비게이션 ───────────────────────────────────────────────────────
    col_prev, _, col_next = st.columns([1, 2, 1])

    with col_prev:
        if st.button("← 이전 (결과 대시보드)", use_container_width=True):
            st.session_state["current_screen"] = 5
            st.rerun()

    with col_next:
        if st.button("다음 (PM 리포트) →", type="primary", use_container_width=True):
            st.session_state["current_screen"] = 7
            st.rerun()
