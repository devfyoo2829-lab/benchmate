"""
BenchMate — Node 7: aggregate_results

전체 채점 결과를 집계하여 다음 3가지를 생성한다:
1. knowledge_scores_final: ab/ba 교차 채점 평균 (Position Bias 제거)
2. summary_table: 모델별 Knowledge 5축 평균 + Agent 4항목 평균
3. judge_reliability: Human Review 완료 항목 기준 ±2점 이내 일치율
4. estimated_cost: model_responses 토큰 수 × pricing.json 단가
"""

import json
import os
from typing import Dict, List, Optional, Tuple

from pipeline.state import (
    AgentScore,
    EvalState,
    HumanReviewItem,
    KnowledgeScore,
    ModelResponse,
)

# pricing.json 경로 (프로젝트 루트 기준)
_PRICING_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "pricing.json"
)


def _load_pricing() -> Dict[str, Dict]:
    """pricing.json을 로드하여 모델명 → 단가 매핑 반환."""
    with open(_PRICING_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return data["models"]


def _find_pricing(model_name: str, pricing: Dict[str, Dict]) -> Dict:
    """
    모델명으로 단가를 조회한다.
    완전 일치 → 부분 일치(소문자) → 'default' 폴백 순서로 탐색.
    """
    # 완전 일치
    if model_name in pricing:
        return pricing[model_name]

    # 소문자 부분 일치 (예: "claude-3-5-sonnet-20241022" → "claude-sonnet")
    lower = model_name.lower()
    for key in pricing:
        if key == "default":
            continue
        if key in lower or lower in key:
            return pricing[key]

    return pricing["default"]


def _compute_final_knowledge_scores(
    ab_list: List[KnowledgeScore],
    ba_list: List[KnowledgeScore],
) -> List[KnowledgeScore]:
    """
    ab/ba 교차 채점 결과를 (question_id, model_name) 기준으로 짝지어
    각 5개 축과 total을 평균 낸 최종 점수 목록을 반환한다.
    ba가 없는 항목은 ab 값을 그대로 사용한다.
    """
    ba_map: Dict[Tuple[str, str], KnowledgeScore] = {
        (s["question_id"], s["model_name"]): s for s in ba_list
    }

    final: List[KnowledgeScore] = []
    for ab in ab_list:
        key = (ab["question_id"], ab["model_name"])
        ba = ba_map.get(key)

        if ba is None:
            # ba 없으면 ab 값 그대로 유지하되 judge_order만 변경
            final.append(KnowledgeScore(
                question_id=ab["question_id"],
                model_name=ab["model_name"],
                accuracy=ab["accuracy"],
                fluency=ab["fluency"],
                hallucination=ab["hallucination"],
                domain_expertise=ab["domain_expertise"],
                utility=ab["utility"],
                total=ab["total"],
                reason=ab["reason"],
                judge_order="final",
            ))
        else:
            accuracy = (ab["accuracy"] + ba["accuracy"]) / 2
            fluency = (ab["fluency"] + ba["fluency"]) / 2
            hallucination = (ab["hallucination"] + ba["hallucination"]) / 2
            domain_expertise = (ab["domain_expertise"] + ba["domain_expertise"]) / 2
            utility = (ab["utility"] + ba["utility"]) / 2
            total = (ab["total"] + ba["total"]) / 2
            final.append(KnowledgeScore(
                question_id=ab["question_id"],
                model_name=ab["model_name"],
                accuracy=accuracy,
                fluency=fluency,
                hallucination=hallucination,
                domain_expertise=domain_expertise,
                utility=utility,
                total=total,
                reason="ab/ba 평균",
                judge_order="final",
            ))

    return final


def _avg(values: List[Optional[float]]) -> Optional[float]:
    """None을 제외한 평균. 유효 값이 없으면 None 반환."""
    valid = [v for v in values if v is not None]
    if not valid:
        return None
    return sum(valid) / len(valid)


def _build_summary_table(
    knowledge_final: List[KnowledgeScore],
    agent_scores: List[AgentScore],
    selected_models: List[str],
) -> Dict:
    """
    모델별 Knowledge 5축 평균 + Agent 4항목 평균을 집계한 summary_table을 생성한다.

    구조:
    {
      "model_name": {
        "knowledge": {
          "total": float | None,
          "accuracy": float | None,
          "fluency": float | None,
          "hallucination": float | None,
          "domain_expertise": float | None,
          "utility": float | None,
          "question_count": int,
        },
        "agent": {
          "call_score": float | None,
          "slot_score": float | None,
          "relevance_score": float | None,
          "completion_score": float | None,
          "scenario_count": int,
        },
      }
    }
    """
    table: Dict = {}

    # 모든 관련 모델 이름 수집 (selected_models + 실제 점수에 등장하는 모델)
    model_names = set(selected_models)
    for s in knowledge_final:
        model_names.add(s["model_name"])
    for s in agent_scores:
        model_names.add(s["model_name"])

    for model in model_names:
        # Knowledge 집계
        k_scores = [s for s in knowledge_final if s["model_name"] == model]
        knowledge_section: Dict = {
            "total": _avg([s["total"] for s in k_scores]),
            "accuracy": _avg([s["accuracy"] for s in k_scores]),
            "fluency": _avg([s["fluency"] for s in k_scores]),
            "hallucination": _avg([s["hallucination"] for s in k_scores]),
            "domain_expertise": _avg([s["domain_expertise"] for s in k_scores]),
            "utility": _avg([s["utility"] for s in k_scores]),
            "question_count": len(k_scores),
        }

        # Agent 집계 (None 제외 평균)
        a_scores = [s for s in agent_scores if s["model_name"] == model]
        agent_section: Dict = {
            "call_score": _avg([s["call_score"] for s in a_scores]),
            "slot_score": _avg([s["slot_score"] for s in a_scores]),
            "relevance_score": _avg([s["relevance_score"] for s in a_scores]),
            "completion_score": _avg([s["completion_score"] for s in a_scores]),
            "scenario_count": len(a_scores),
        }

        table[model] = {
            "knowledge": knowledge_section,
            "agent": agent_section,
        }

    return table


def _compute_judge_reliability(
    human_review_queue: List[HumanReviewItem],
) -> Optional[float]:
    """
    is_reviewed=True인 항목에서 Judge 점수와 Human 점수의 차이가 ±2 이내인 비율(%).
    검토 완료 항목이 없으면 None 반환.

    Knowledge: judge_score["total"] vs sum(non-None human_score 수치 필드)
    Agent: judge_score["call_score"] vs human_score["call_score"]
    """
    reviewed = [r for r in human_review_queue if r.get("is_reviewed") and r.get("human_score")]
    if not reviewed:
        return None

    agreed = 0
    for r in reviewed:
        judge_score: Dict = r["judge_score"]
        human_score: Dict = r["human_score"]
        item_type: str = r["item_type"]

        if item_type == "knowledge":
            judge_total = judge_score.get("total")
            if judge_total is None:
                # total 필드 없으면 5개 축 합산
                axes = ["accuracy", "fluency", "hallucination", "domain_expertise", "utility"]
                judge_total = sum(
                    judge_score.get(ax, 0) or 0 for ax in axes
                )
            human_axes = ["accuracy", "fluency", "hallucination", "domain_expertise", "utility"]
            human_total = sum(
                human_score.get(ax) or 0 for ax in human_axes
                if human_score.get(ax) is not None
            )
        else:  # agent
            judge_total = judge_score.get("call_score", 0) or 0
            human_total = human_score.get("call_score") or 0

        if abs(judge_total - human_total) <= 2:
            agreed += 1

    return round((agreed / len(reviewed)) * 100, 1)


def _compute_estimated_cost(
    model_responses: List[ModelResponse],
    pricing: Dict[str, Dict],
) -> Dict[str, float]:
    """
    모델별 총 입력/출력 토큰 수를 합산하고 pricing.json 단가를 적용해
    추정 비용(USD)을 계산한다.

    반환:
    {
      "model_name": cost_usd,       # 모델별 비용
      "_total": total_cost_usd,     # 전체 합계
    }
    """
    # 모델별 토큰 합산
    token_usage: Dict[str, Dict[str, int]] = {}
    for resp in model_responses:
        model = resp["model_name"]
        if model not in token_usage:
            token_usage[model] = {"input_tokens": 0, "output_tokens": 0}
        token_usage[model]["input_tokens"] += resp.get("input_tokens", 0) or 0
        token_usage[model]["output_tokens"] += resp.get("output_tokens", 0) or 0

    cost_map: Dict[str, float] = {}
    total_cost = 0.0

    for model, usage in token_usage.items():
        rate = _find_pricing(model, pricing)
        cost = (
            usage["input_tokens"] * rate["input_per_1k"] / 1000
            + usage["output_tokens"] * rate["output_per_1k"] / 1000
        )
        cost = round(cost, 6)
        cost_map[model] = cost
        total_cost += cost

    cost_map["_total"] = round(total_cost, 6)
    return cost_map


def aggregate_results(state: EvalState) -> dict:
    """
    채점 결과 집계 노드.

    입력:
        knowledge_scores_ab, knowledge_scores_ba  — ab/ba 교차 채점 목록
        agent_scores                              — Agent 채점 목록
        human_review_queue                        — Human Review 큐
        selected_models                           — 선택된 모델 목록
        model_responses                           — 전체 모델 응답 (토큰 수 포함)

    출력:
        knowledge_scores_final  — ab/ba 평균 최종 점수
        summary_table           — 모델별 Knowledge/Agent 집계
        judge_reliability       — Judge-Human 일치율 (%)
        estimated_cost          — 모델별 추정 비용 (USD)
    """
    ab_list: List[KnowledgeScore] = state.get("knowledge_scores_ab", [])
    ba_list: List[KnowledgeScore] = state.get("knowledge_scores_ba", [])
    agent_scores: List[AgentScore] = state.get("agent_scores", [])
    human_review_queue: List[HumanReviewItem] = state.get("human_review_queue", [])
    selected_models: List[str] = state.get("selected_models", [])
    model_responses: List[ModelResponse] = state.get("model_responses", [])

    # 1. Knowledge 최종 점수 (ab/ba 평균)
    knowledge_scores_final = _compute_final_knowledge_scores(ab_list, ba_list)

    # 2. summary_table
    summary_table = _build_summary_table(
        knowledge_scores_final, agent_scores, selected_models
    )

    # 3. judge_reliability
    judge_reliability = _compute_judge_reliability(human_review_queue)

    # 4. estimated_cost
    try:
        pricing = _load_pricing()
    except (FileNotFoundError, KeyError, json.JSONDecodeError):
        pricing = {"default": {"input_per_1k": 0.001, "output_per_1k": 0.003}}
    estimated_cost = _compute_estimated_cost(model_responses, pricing)

    return {
        "knowledge_scores_final": knowledge_scores_final,
        "summary_table": summary_table,
        "judge_reliability": judge_reliability,
        "estimated_cost": estimated_cost,
    }
