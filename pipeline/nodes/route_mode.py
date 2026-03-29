"""
Node 2. route_mode
책임: eval_mode 값을 확인하고 integrated 모드 초기 단계를 설정한다.
실제 분기 결정은 graph.py의 decide_branch 함수가 담당한다.
설계 기준: docs/BenchMate_Agent설계.md §3 Node 2, §4
"""

from pipeline.state import EvalState


def route_mode(state: EvalState) -> dict:
    """eval_mode를 읽어 라우팅 준비만 수행한다.

    - knowledge / agent 모드: EvalState 변경 없이 {} 반환
    - integrated 모드: _integrated_phase가 미설정인 경우에만 "knowledge"로 초기화
      (graph.py decide_branch가 이 값을 읽어 분기 결정)
    """
    if state["eval_mode"] == "integrated":
        # _integrated_phase가 아직 설정되지 않은 경우에만 초기화
        # (integrated 모드 재진입 시 기존 값 보존)
        if not state.get("_integrated_phase"):  # type: ignore[call-overload]
            return {"_integrated_phase": "knowledge"}

    return {}
