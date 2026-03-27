"""
BenchMate — evaluate_call 핵심 로직
설계 기준: docs/BenchMate_Agent설계.md §3 Node 4b

책임:
  - 모델 raw_output을 JSON 파싱 (마크다운 코드블록 제거 후 재시도 포함)
  - Tool 이름 snake_case 정규화 후 정답과 비교
  - 파라미터 값 비교 시 타입 캐스팅 허용 ("720" == 720 → True)
  - 채점 결과를 AgentScore 형태의 dict로 반환
"""

import json
import re
from typing import Any, Dict, List, Optional


# ── 정규화 헬퍼 ────────────────────────────────────────────────────────────────


def _to_snake_case(name: str) -> str:
    """camelCase / PascalCase / kebab-case 를 snake_case 로 변환."""
    # kebab-case → snake_case
    name = name.replace("-", "_")
    # camelCase / PascalCase 경계 삽입
    name = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    name = re.sub(r"([a-z\d])([A-Z])", r"\1_\2", name)
    return name.lower()


def normalize_tool_name(name: str) -> str:
    """Tool 이름을 소문자 snake_case 로 정규화."""
    return _to_snake_case(name.strip())


# ── JSON 파싱 헬퍼 ─────────────────────────────────────────────────────────────


def _strip_markdown_code_block(text: str) -> str:
    """```json ... ``` 또는 ``` ... ``` 코드블록 제거."""
    cleaned = re.sub(r"```(?:json)?\s*", "", text)
    return cleaned.replace("```", "").strip()


def try_parse_json(raw: str) -> Optional[Dict[str, Any]]:
    """raw 문자열을 JSON 파싱. 실패 시 마크다운 제거 후 재시도. 최종 실패 시 None."""
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        pass

    cleaned = _strip_markdown_code_block(raw)
    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, TypeError):
        return None


# ── 파라미터 비교 ──────────────────────────────────────────────────────────────


def _values_equal(extracted: Any, expected: Any) -> bool:
    """두 값을 str 캐스팅 후 비교 (타입 캐스팅 허용: "720" == 720 → True)."""
    return str(extracted).strip() == str(expected).strip()


def compare_parameters(
    extracted: Dict[str, Any],
    expected: Dict[str, Any],
) -> tuple[bool, List[str], List[str]]:
    """파라미터 dict 비교.

    Returns:
        (params_match, missing_params, extra_params)
        - params_match: 정답 파라미터가 모두 존재하고 값도 일치하면 True
        - missing_params: 정답에 있으나 모델이 누락한 키 목록
        - extra_params: 정답에 없으나 모델이 추가한 키 목록
    """
    missing: List[str] = [k for k in expected if k not in extracted]
    extra: List[str] = [k for k in extracted if k not in expected]

    value_match = all(
        _values_equal(extracted[k], expected[k])
        for k in expected
        if k in extracted
    )
    params_match = (len(missing) == 0 and len(extra) == 0 and value_match)
    return params_match, missing, extra


# ── 메인 채점 함수 ─────────────────────────────────────────────────────────────


def evaluate_single_call(
    expected: Dict[str, Any],
    raw_output: str,
    scenario_id: str,
    turn_index: int,
    model_name: str,
) -> Dict[str, Any]:
    """단일 Tool 호출을 채점하여 AgentScore 호환 dict 반환.

    Args:
        expected: scenario의 expected_tool_calls 원소.
                  {"tool_name": str, "parameters": dict}
        raw_output: 모델이 생성한 원본 문자열
        scenario_id: 채점 대상 시나리오 ID
        turn_index: 해당 턴 인덱스
        model_name: 채점 대상 모델 이름

    Returns:
        AgentScore 호환 dict.
        slot_score / relevance_score / completion_score 는 None (judge_agent 에서 채움).
    """
    parsed = try_parse_json(raw_output)

    # JSON 파싱 완전 실패
    if parsed is None:
        return {
            "scenario_id": scenario_id,
            "turn_index": turn_index,
            "model_name": model_name,
            "tool_name_extracted": None,
            "params_extracted": None,
            "call_correct": False,
            "params_match": False,
            "missing_params": list(expected.get("parameters", {}).keys()),
            "extra_params": [],
            "call_score": 0,
            "slot_score": None,
            "relevance_score": None,
            "completion_score": None,
            "reason": "JSON 파싱 실패",
            "_parse_failed": True,
        }

    extracted_name: str = parsed.get("tool_name", "")
    extracted_params: Dict[str, Any] = parsed.get("parameters", {})
    expected_name: str = expected.get("tool_name", "")
    expected_params: Dict[str, Any] = expected.get("parameters", {})

    name_match = normalize_tool_name(extracted_name) == normalize_tool_name(expected_name)
    params_match, missing, extra = compare_parameters(extracted_params, expected_params)

    call_score = 1 if (name_match and params_match) else 0

    if call_score == 1:
        reason = "정확"
    else:
        parts: List[str] = []
        if not name_match:
            parts.append(f"tool 불일치: {extracted_name!r} ≠ {expected_name!r}")
        if missing:
            parts.append(f"누락 파라미터: {missing}")
        if extra:
            parts.append(f"불필요 파라미터: {extra}")
        reason = ", ".join(parts) if parts else "파라미터 값 불일치"

    return {
        "scenario_id": scenario_id,
        "turn_index": turn_index,
        "model_name": model_name,
        "tool_name_extracted": extracted_name,
        "params_extracted": extracted_params,
        "call_correct": name_match,
        "params_match": params_match,
        "missing_params": missing,
        "extra_params": extra,
        "call_score": call_score,
        "slot_score": None,
        "relevance_score": None,
        "completion_score": None,
        "reason": reason,
        "_parse_failed": False,
    }
