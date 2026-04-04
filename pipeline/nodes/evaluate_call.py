"""
Node 4b: evaluate_call
model_responses에서 Tool 호출 raw_output을 파싱하여
코드 기반 채점(call_score)을 수행한다.
설계 기준: docs/BenchMate_Agent설계.md — Node 4b
"""

from pipeline.state import EvalState
from evaluators.tool_call_evaluator import evaluate_single_call, try_parse_json


def evaluate_call(state: EvalState) -> dict:
    scenario_map = {s["id"]: s for s in state["scenarios"]}
    agent_scores = []

    for response in state["model_responses"]:
        scenario = scenario_map.get(response["item_id"])
        if scenario is None:
            continue

        raw_output = response.get("raw_output") or ""
        expected_calls = scenario["expected_tool_calls"]

        if expected_calls:
            # single_A / multi: 정상 Tool 호출 비교
            for expected_call in expected_calls:
                turn_index = expected_call.get("turn_index", 0)
                score = evaluate_single_call(
                    expected=expected_call,
                    raw_output=raw_output,
                    scenario_id=scenario["id"],
                    turn_index=turn_index,
                    model_name=response["model_name"],
                )
                agent_scores.append(score)
        else:
            # single_B / single_C: 도구 호출이 없어야 정답
            # → 자리표시자 AgentScore 생성 후 judge_agent가 slot/relevance 채움
            parsed = try_parse_json(raw_output)
            has_tool_call = parsed is not None and "tool_name" in parsed
            no_tool_call = not has_tool_call
            print(
                f"[evaluate_call] scenario={scenario['id']!r} "
                f"type={scenario['scenario_type']!r} "
                f"model={response['model_name']!r} "
                f"raw={raw_output[:60]!r} "
                f"no_tool_call={no_tool_call}"
            )
            agent_scores.append({
                "scenario_id":        scenario["id"],
                "turn_index":         0,
                "model_name":         response["model_name"],
                "tool_name_extracted": (parsed or {}).get("tool_name"),
                "params_extracted":    (parsed or {}).get("parameters"),
                "call_correct":        no_tool_call,
                "params_match":        no_tool_call,
                "missing_params":      [],
                "extra_params":        [],
                "call_score":          1 if no_tool_call else 0,
                "slot_score":          None,
                "relevance_score":     None,
                "completion_score":    None,
                "reason":              "올바른 비호출" if no_tool_call else "잘못된 도구 호출 시도",
                "_parse_failed":       False,
            })

    return {"agent_scores": agent_scores}
