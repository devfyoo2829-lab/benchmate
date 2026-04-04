"""
BenchMate — Screen 6: Human Review
담당자가 AI 채점 결과를 검토·수정하는 인터페이스.
같은 question_id/scenario_id에 대해 여러 모델이 등록된 경우 문항 기준으로 그룹핑 표시.
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

# 내부 review_reason 값 → 사용자 친화적 표현
_REASON_LABELS: dict[str, str] = {
    "Judge JSON 파싱 3회 실패":    "AI 채점 오류 발생 항목",
    "hallucination 점수 낮음":     "허위 정보 생성 가능성이 감지된 항목",
    "랜덤 품질 샘플":              "AI 채점 품질 확인용 무작위 선정 항목",
    "교차 편차":                   "AI 채점 간 점수 차이가 큰 항목",
    "Tool 호출 실패":              "AI가 도구 호출에 실패한 항목",
}


def _reason_label(reason: str) -> str:
    """review_reason을 사용자 친화적 문구로 변환한다."""
    for key, label in _REASON_LABELS.items():
        if key in reason:
            return label
    return reason or "검토 대상 항목"


# ── judge_reliability 계산 ────────────────────────────────────────────────────

def _calc_judge_reliability(queue: list[dict]) -> float:
    """
    Human Review가 완료된 항목들의 AI-담당자 일치율(%)을 계산한다.
    Knowledge: judge_score["total"] vs sum(human_score 5개 축)
               |차이| <= 2 이면 일치.
    Agent: call_score 일치 여부.
    """
    reviewed = [r for r in queue if r.get("is_reviewed") and r.get("human_score")]
    if not reviewed:
        return 100.0

    agreed = 0
    for r in reviewed:
        j = r.get("judge_score", {})
        h = r.get("human_score", {})
        item_type = r.get("item_type", "knowledge")

        if item_type == "knowledge":
            j_total = j.get("total", 0) or 0
            h_total = sum([
                h.get("accuracy") or 0,
                h.get("fluency") or 0,
                h.get("hallucination") or 0,
                h.get("domain_expertise") or 0,
                h.get("utility") or 0,
            ])
        else:
            j_total = j.get("call_score") or 0
            h_total = h.get("call_score") or 0

        if abs(j_total - h_total) <= 2:
            agreed += 1

    return round((agreed / len(reviewed)) * 100, 1)


def _update_reliability(updated_queue: list[dict]) -> None:
    """검토 완료 항목 기준으로 judge_reliability를 즉시 계산·저장한다."""
    if "eval_result" not in st.session_state:
        return

    reliability = _calc_judge_reliability(updated_queue)

    result = dict(st.session_state["eval_result"])
    result["judge_reliability"] = reliability
    result["human_review_queue"] = updated_queue
    st.session_state["eval_result"] = result
    st.session_state["judge_reliability"] = reliability


# ── 모델 응답 / 루브릭 조회 ──────────────────────────────────────────────────

_API_ERROR_PATTERNS = ("Error code: 404", "not_found_error")


def _is_api_error(text: str) -> bool:
    return any(p in text for p in _API_ERROR_PATTERNS)


def _find_response_text(eval_result: dict, item_id: str, model_name: str) -> str:
    """eval_result["model_responses"]에서 item_id + model_name에 맞는 response_text를 반환.
    raw_output에 API 오류가 포함된 경우 빈 문자열을 반환한다."""
    for record in (eval_result or {}).get("model_responses") or []:
        rid = record.get("question_id") or record.get("scenario_id") or record.get("item_id", "")
        if rid == item_id and record.get("model_name") == model_name:
            raw = record.get("raw_output") or ""
            if _is_api_error(raw):
                return ""
            return (
                record.get("response_text")
                or raw
                or record.get("response")
                or ""
            )
    return ""


def _find_raw_output(eval_result: dict, item_id: str, model_name: str) -> str:
    """raw_output 원문 반환 (API 오류 감지용)."""
    for record in (eval_result or {}).get("model_responses") or []:
        rid = record.get("question_id") or record.get("scenario_id") or record.get("item_id", "")
        if rid == item_id and record.get("model_name") == model_name:
            return record.get("raw_output") or ""
    return ""


def _find_instance_rubric(eval_result: dict, item_id: str) -> str:
    """eval_result["questions"]에서 item_id와 일치하는 instance_rubric을 반환."""
    for record in (eval_result or {}).get("questions") or []:
        qid = record.get("question_id") or record.get("id") or record.get("item_id", "")
        if qid == item_id:
            return record.get("instance_rubric") or ""
    return ""


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

def _render_knowledge_form(form_key: str, item: dict) -> dict | None:
    judge_score: dict = item.get("judge_score", {})

    st.markdown("**AI 채점 결과**")
    cols = st.columns(len(_KNOWLEDGE_FIELDS))
    for col, (key, label) in zip(cols, _KNOWLEDGE_FIELDS):
        with col:
            st.metric(label=label, value=judge_score.get(key, "—"))

    reason = judge_score.get("reason", "")
    if reason:
        st.caption(f"AI 채점 이유: {reason}")

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
                key=f"s6_slider_{form_key}_{key}",
            )

    if st.button("검토 완료", key=f"s6_submit_{form_key}", type="primary"):
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

def _render_agent_form(form_key: str, item: dict) -> dict | None:
    judge_score: dict = item.get("judge_score", {})
    judge_call = judge_score.get("call_score", "—")

    st.metric(label="도구 호출 정확도 (AI 채점)", value=str(judge_call))

    reason = judge_score.get("reason", "")
    if reason:
        st.caption(f"AI 채점 이유: {reason}")

    default_idx = 0 if judge_call != 1 else 1
    human_call = st.radio(
        "담당자 판단 (0: 틀림 / 1: 맞음)",
        options=[0, 1],
        format_func=lambda x: "0 (AI가 잘못 호출함)" if x == 0 else "1 (AI가 올바르게 호출함)",
        index=default_idx,
        horizontal=True,
        key=f"s6_radio_{form_key}",
    )

    if st.button("검토 완료", key=f"s6_submit_{form_key}", type="primary"):
        return {
            "accuracy":         None,
            "fluency":          None,
            "hallucination":    None,
            "domain_expertise": None,
            "utility":          None,
            "call_score":       human_call,
        }
    return None


# ── 그룹 단위 렌더 ────────────────────────────────────────────────────────────

def _render_group(
    group_idx: int,
    item_id: str,
    group: list[dict],
    queue: list[dict],
) -> None:
    """같은 item_id를 공유하는 항목들을 하나의 expander 안에서 표시한다."""
    all_reviewed = all(item.get("is_reviewed") for item in group)
    item_type = group[0].get("item_type", "knowledge")
    label = f"{'✅' if all_reviewed else '⬜'} [{group_idx + 1}] {item_id}"

    eval_result: dict = st.session_state.get("eval_result") or {}

    with st.expander(label, expanded=not all_reviewed):
        # 문항 루브릭 (item_id 공통) 표시
        rubric = _find_instance_rubric(eval_result, item_id)
        if rubric:
            st.caption(f"채점 기준: {rubric}")

        for item in group:
            model_name: str = item.get("model_name", "unknown")
            review_reason: str = item.get("review_reason", "")
            is_reviewed: bool = item.get("is_reviewed", False)

            st.markdown(
                f"**모델: `{model_name}`** — "
                f"검토 사유: {_reason_label(review_reason)}"
            )

            # 모델 응답 표시 (Knowledge: response_text, Agent: raw_output 우선)
            response_text = _find_response_text(eval_result, item_id, model_name)
            raw_output    = _find_raw_output(eval_result, item_id, model_name)

            if not response_text and _is_api_error(raw_output):
                st.warning(
                    "⚠️ 이 모델은 API 오류로 응답을 가져오지 못했습니다.\n\n"
                    "(원인: 모델명 오류 또는 API 크레딧 부족)"
                )
            elif response_text or item_type == "agent":
                st.text_area(
                    "모델이 실제로 답변한 내용:",
                    value=response_text or "모델 응답을 찾을 수 없습니다.",
                    height=300,
                    disabled=True,
                    key=f"s6_resp_{group_idx}_{model_name}",
                )

            if is_reviewed:
                col_status, col_edit = st.columns([3, 1])
                with col_status:
                    st.success("검토 완료")
                with col_edit:
                    if st.button("수정하기", key=f"s6_edit_{group_idx}_{model_name}"):
                        item["is_reviewed"] = False
                        _update_reliability(queue)
                        st.rerun()

                human_score = item.get("human_score") or {}
                if item_type == "knowledge":
                    score_cols = st.columns(len(_KNOWLEDGE_FIELDS))
                    for col, (key, label_txt) in zip(score_cols, _KNOWLEDGE_FIELDS):
                        with col:
                            st.metric(label=label_txt, value=human_score.get(key, "—"))
                else:
                    st.metric(
                        label="담당자 판단 call_score",
                        value=str(human_score.get("call_score", "—")),
                    )
            else:
                form_key = f"{group_idx}_{model_name}"
                if item_type == "knowledge":
                    result = _render_knowledge_form(form_key, item)
                else:
                    result = _render_agent_form(form_key, item)

                if result is not None:
                    item["human_score"] = result
                    item["is_reviewed"] = True
                    _update_reliability(queue)
                    st.rerun()

            st.markdown("---")


# ── render ────────────────────────────────────────────────────────────────────

def render() -> None:
    st.title("BenchMate")
    st.write("Human Review — AI 채점 결과 검토 및 수정")
    st.divider()

    st.info(
        "AI가 채점한 결과를 담당자가 직접 검토하는 단계입니다.\n\n"
        "AI 채점이 적절했는지 확인하고, 점수가 잘못됐다고 판단되면 수정해주세요.\n\n"
        "검토를 완료하면 'AI 채점 신뢰도'가 자동으로 계산됩니다.\n\n"
        "모든 항목 검토 후 다음 단계로 넘어가세요."
    )

    eval_result: dict | None = st.session_state.get("eval_result")
    queue: list[dict] = (eval_result or {}).get("human_review_queue") or []

    if not queue:
        _render_empty_state()
        return

    reviewed_count = sum(1 for item in queue if item.get("is_reviewed"))
    total_count = len(queue)
    st.caption(f"검토 진행: {reviewed_count} / {total_count}")
    st.progress(reviewed_count / total_count if total_count else 0)

    # ── 검토 완료된 항목이 있으면 신뢰도 표시 ────────────────────────────────
    saved_reliability = st.session_state.get("judge_reliability")
    if saved_reliability is not None:
        label_txt = (
            "전체 검토 완료 — AI 채점 신뢰도"
            if reviewed_count == total_count
            else "현재까지 AI 채점 신뢰도"
        )
        st.success(f"{label_txt}: {saved_reliability:.1f}%")

    st.divider()

    # ── item_id 기준으로 그룹핑 (순서 유지) ──────────────────────────────────
    groups: dict[str, list[dict]] = {}
    for item in queue:
        item_id = item.get("item_id", "")
        groups.setdefault(item_id, []).append(item)

    for group_idx, (item_id, group) in enumerate(groups.items()):
        _render_group(group_idx, item_id, group, queue)

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
