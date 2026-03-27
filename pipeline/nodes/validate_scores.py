"""
Node 5. validate_scores

Judge 출력 JSON 파싱 검증 및 재시도 분기.
- _parse_failed=True 항목 감지
- retry_count < 3: retry_count 증가 + last_failed_branch 설정
- retry_count >= 3: 해당 항목을 human_review_queue에 강제 등록
- 파싱 성공 시: retry_count=0, last_failed_branch=None 반환
"""

from typing import List

from pipeline.state import EvalState, HumanReviewItem


def validate_scores(state: EvalState) -> dict:
    failed_knowledge: List = [
        s for s in state["knowledge_scores_ab"] if s.get("_parse_failed")
    ] + [
        s for s in state["knowledge_scores_ba"] if s.get("_parse_failed")
    ]
    failed_agent: List = [
        s for s in state["agent_scores"] if s.get("_parse_failed")
    ]

    all_failed = failed_knowledge + failed_agent

    if not all_failed:
        return {"retry_count": 0, "last_failed_branch": None}

    if state["retry_count"] < 3:
        failed_branch = "knowledge" if failed_knowledge else "agent"
        return {
            "retry_count": state["retry_count"] + 1,
            "last_failed_branch": failed_branch,
            "_retry_targets": all_failed,
        }

    # retry_count >= 3: Human Review 큐 강제 등록
    forced_reviews: List[HumanReviewItem] = []
    for s in failed_knowledge:
        forced_reviews.append(HumanReviewItem(
            item_id=s["question_id"],
            item_type="knowledge",
            model_name=s["model_name"],
            judge_score=dict(s),
            human_score=None,
            review_reason="Judge JSON 파싱 3회 실패",
            is_reviewed=False,
        ))
    for s in failed_agent:
        forced_reviews.append(HumanReviewItem(
            item_id=s["scenario_id"],
            item_type="agent",
            model_name=s["model_name"],
            judge_score=dict(s),
            human_score=None,
            review_reason="Judge JSON 파싱 3회 실패",
            is_reviewed=False,
        ))

    return {
        "human_review_queue": state["human_review_queue"] + forced_reviews,
        "retry_count": 0,
        "last_failed_branch": None,
    }
