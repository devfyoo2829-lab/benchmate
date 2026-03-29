"""
Node 4b: evaluate_call
model_responses에서 Tool 호출 raw_output을 파싱하여
코드 기반 채점(call_score)을 수행한다.
설계 기준: docs/BenchMate_Agent설계.md — Node 4b
"""

from pipeline.state import EvalState
from evaluators.tool_call_evaluator import evaluate_single_call


def evaluate_call(state: EvalState) -> dict:
    scenario_map = {s["id"]: s for s in state["scenarios"]}
    agent_scores = []

    for response in state["model_responses"]:
        scenario = scenario_map.get(response["item_id"])
        if scenario is None:
            continue

        raw_output = response.get("raw_output") or ""

        for expected_call in scenario["expected_tool_calls"]:
            turn_index = expected_call.get("turn_index", 0)
            score = evaluate_single_call(
                expected=expected_call,
                raw_output=raw_output,
                scenario_id=scenario["id"],
                turn_index=turn_index,
                model_name=response["model_name"],
            )
            agent_scores.append(score)

    return {"agent_scores": agent_scores}
