"""
BenchMate — Node 6: flag_human_review
선별 기준을 충족하는 항목을 Human Review 큐에 추가한다.

선별 기준 (OR 조건):
1. Knowledge 교차 평가 편차 |ab_total - ba_total| >= 3점
2. hallucination 점수 <= 2 (ab 또는 ba)
3. Agent call_score == 0
4. 전체 문항·시나리오의 랜덤 20% 샘플
"""

import random
from typing import Dict, List, Optional, Tuple

from pipeline.state import AgentScore, EvalState, HumanReviewItem, KnowledgeScore


def _already_queued(queue: List[HumanReviewItem], item_id: str, model_name: str) -> bool:
    """Human Review 큐에 동일 (item_id, model_name) 조합이 이미 있는지 확인."""
    return any(r["item_id"] == item_id and r["model_name"] == model_name for r in queue)


def _should_flag_knowledge(
    ab: KnowledgeScore, ba: Optional[KnowledgeScore]
) -> Tuple[bool, str]:
    """Knowledge 항목 선별 — OR 조건 3가지."""
    # 1. 교차 평가 편차 >= 3점
    if ba is not None and abs(ab["total"] - ba["total"]) >= 3:
        return True, f"교차 편차 {abs(ab['total'] - ba['total'])}점"

    # 2. hallucination 점수 <= 2
    ab_low = ab["hallucination"] <= 2
    ba_low = ba is not None and ba["hallucination"] <= 2
    if ab_low or ba_low:
        return True, "hallucination 점수 낮음"

    # 4. 랜덤 20% 샘플
    if random.random() < 0.20:
        return True, "랜덤 품질 샘플"

    return False, ""


def _should_flag_agent(score: AgentScore) -> Tuple[bool, str]:
    """Agent 항목 선별 — OR 조건 2가지."""
    # 3. call_score == 0
    if score["call_score"] == 0:
        return True, "Tool 호출 실패"

    # 4. 랜덤 20% 샘플
    if random.random() < 0.20:
        return True, "랜덤 품질 샘플"

    return False, ""


def flag_human_review(state: EvalState) -> dict:
    """
    선별 기준을 충족하는 Knowledge/Agent 항목을 Human Review 큐에 추가한다.
    validate_scores 노드가 강제 등록한 항목(파싱 실패)은 유지하며 중복 등록하지 않는다.
    """
    existing_queue: List[HumanReviewItem] = list(state["human_review_queue"])
    new_items: List[HumanReviewItem] = []

    # ── Knowledge 항목 처리 ──────────────────────────────────────────────────────
    ab_scores: List[KnowledgeScore] = state.get("knowledge_scores_ab", [])
    ba_scores: List[KnowledgeScore] = state.get("knowledge_scores_ba", [])

    # ba 점수를 (question_id, model_name) 키로 조회하기 위한 맵
    ba_map: Dict[Tuple[str, str], KnowledgeScore] = {
        (s["question_id"], s["model_name"]): s for s in ba_scores
    }

    for ab in ab_scores:
        qid = ab["question_id"]
        model = ab["model_name"]

        if _already_queued(existing_queue, qid, model) or _already_queued(new_items, qid, model):
            continue

        ba = ba_map.get((qid, model))
        flagged, reason = _should_flag_knowledge(ab, ba)

        if flagged:
            new_items.append(HumanReviewItem(
                item_id=qid,
                item_type="knowledge",
                model_name=model,
                judge_score=dict(ab),
                human_score=None,
                review_reason=reason,
                is_reviewed=False,
            ))

    # ── Agent 항목 처리 ──────────────────────────────────────────────────────────
    agent_scores: List[AgentScore] = state.get("agent_scores", [])

    for score in agent_scores:
        sid = score["scenario_id"]
        model = score["model_name"]

        if _already_queued(existing_queue, sid, model) or _already_queued(new_items, sid, model):
            continue

        flagged, reason = _should_flag_agent(score)

        if flagged:
            new_items.append(HumanReviewItem(
                item_id=sid,
                item_type="agent",
                model_name=model,
                judge_score=dict(score),
                human_score=None,
                review_reason=reason,
                is_reviewed=False,
            ))

    return {"human_review_queue": existing_queue + new_items}
