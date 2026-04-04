"""
BenchMate — Supabase 클라이언트 및 평가 결과 저장 모듈.
평가 완료 후 EvalState 데이터를 6개 테이블에 순차 저장한다.
"""

import os
from typing import Dict, List, Optional

from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

_client: Optional[Client] = None


def _get_client() -> Client:
    global _client
    if _client is None:
        url = os.environ["SUPABASE_URL"]
        key = os.environ["SUPABASE_ANON_KEY"]
        _client = create_client(url, key)
    return _client


def _best_model(summary_table: Optional[Dict]) -> Optional[str]:
    """summary_table에서 Knowledge 총점이 가장 높은 모델 이름 반환."""
    if not summary_table:
        return None
    best, best_score = None, -1.0
    for model, sections in summary_table.items():
        total = sections.get("knowledge", {}).get("total")
        if total is not None and total > best_score:
            best_score = total
            best = model
    return best


def save_eval_session(eval_result: dict) -> None:
    """
    평가 완료 후 EvalState(+ pm_report_text 포함) dict를 Supabase 6개 테이블에 저장.

    각 단계는 독립적으로 try/except 처리되어 실패해도 다음 단계를 진행한다.
    """
    client = _get_client()
    session_id: str = eval_result.get("eval_session_id", "")

    # ① eval_sessions
    try:
        row = {
            "session_id":        session_id,
            "eval_mode":         eval_result.get("eval_mode", ""),
            "domain":            eval_result.get("domain", ""),
            "selected_models":   eval_result.get("selected_models"),
            "judge_reliability": eval_result.get("judge_reliability"),
            "estimated_cost":    eval_result.get("estimated_cost"),
            "summary_table":     eval_result.get("summary_table"),
        }
        client.table("eval_sessions").upsert(row, on_conflict="session_id").execute()
        print(f"[Supabase] ① eval_sessions 저장 완료: {session_id}")
    except Exception as e:
        print(f"[Supabase] ① eval_sessions 저장 실패: {e}")

    # ② model_responses
    try:
        responses: List[Dict] = eval_result.get("model_responses") or []
        if responses:
            rows = [
                {
                    "session_id":       session_id,
                    "model_name":       r.get("model_name", ""),
                    "item_id":          r.get("item_id", ""),
                    "response_text":    r.get("response_text"),
                    "tool_call_output": r.get("tool_call_output"),
                    "latency_ms":       r.get("latency_ms"),
                    "input_tokens":     r.get("input_tokens"),
                    "output_tokens":    r.get("output_tokens"),
                    "status":           r.get("status"),
                }
                for r in responses
            ]
            client.table("model_responses").insert(rows).execute()
            print(f"[Supabase] ② model_responses 저장 완료: {len(rows)}건")
    except Exception as e:
        print(f"[Supabase] ② model_responses 저장 실패: {e}")

    # ③ knowledge_scores (final만 저장)
    try:
        k_scores: List[Dict] = eval_result.get("knowledge_scores_final") or []
        if k_scores:
            rows = [
                {
                    "session_id":       session_id,
                    "model_name":       s.get("model_name", ""),
                    "question_id":      s.get("question_id", ""),
                    "accuracy":         s.get("accuracy"),
                    "fluency":          s.get("fluency"),
                    "hallucination":    s.get("hallucination"),
                    "domain_expertise": s.get("domain_expertise"),
                    "utility":          s.get("utility"),
                    "total":            s.get("total"),
                    "judge_order":      "final",
                    "reason":           s.get("reason"),
                }
                for s in k_scores
            ]
            client.table("knowledge_scores").insert(rows).execute()
            print(f"[Supabase] ③ knowledge_scores 저장 완료: {len(rows)}건")
    except Exception as e:
        print(f"[Supabase] ③ knowledge_scores 저장 실패: {e}")

    # ④ agent_scores
    try:
        a_scores: List[Dict] = eval_result.get("agent_scores") or []
        if a_scores:
            rows = [
                {
                    "session_id":       session_id,
                    "model_name":       s.get("model_name", ""),
                    "scenario_id":      s.get("scenario_id", ""),
                    "call_score":       s.get("call_score"),
                    "slot_score":       s.get("slot_score"),
                    "relevance_score":  s.get("relevance_score"),
                    "completion_score": s.get("completion_score"),
                    "reason":           s.get("reason"),
                }
                for s in a_scores
            ]
            client.table("agent_scores").insert(rows).execute()
            print(f"[Supabase] ④ agent_scores 저장 완료: {len(rows)}건")
    except Exception as e:
        print(f"[Supabase] ④ agent_scores 저장 실패: {e}")

    # ⑤ human_reviews
    try:
        queue: List[Dict] = eval_result.get("human_review_queue") or []
        if queue:
            rows = [
                {
                    "session_id":    session_id,
                    "item_id":       item.get("item_id", ""),
                    "item_type":     item.get("item_type", ""),
                    "model_name":    item.get("model_name", ""),
                    "judge_score":   item.get("judge_score"),
                    "human_score":   item.get("human_score"),
                    "review_reason": item.get("review_reason", ""),
                    "is_reviewed":   item.get("is_reviewed", False),
                }
                for item in queue
            ]
            client.table("human_reviews").insert(rows).execute()
            print(f"[Supabase] ⑤ human_reviews 저장 완료: {len(rows)}건")
    except Exception as e:
        print(f"[Supabase] ⑤ human_reviews 저장 실패: {e}")

    # ⑥ eval_reports
    try:
        report_row = {
            "session_id":     session_id,
            "pm_report_text": eval_result.get("pm_report_text"),
            "best_model":     _best_model(eval_result.get("summary_table")),
        }
        client.table("eval_reports").insert(report_row).execute()
        print(f"[Supabase] ⑥ eval_reports 저장 완료")
    except Exception as e:
        print(f"[Supabase] ⑥ eval_reports 저장 실패: {e}")
