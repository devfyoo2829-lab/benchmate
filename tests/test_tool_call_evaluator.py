"""
tests/test_tool_call_evaluator.py
evaluators/tool_call_evaluator.py 단위 테스트
"""

import json
import pytest

from evaluators.tool_call_evaluator import (
    compare_parameters,
    evaluate_single_call,
    normalize_tool_name,
    try_parse_json,
)

# ── 공통 픽스처 ────────────────────────────────────────────────────────────────

EXPECTED_CALL = {
    "tool_name": "search_loan_rate",
    "parameters": {"loan_type": "personal", "amount": 5000000},
}

SCENARIO_ID = "fin_sc_001"
TURN_INDEX = 0
MODEL_NAME = "solar-pro"


def _raw(tool_name: str, parameters: dict) -> str:
    return json.dumps({"tool_name": tool_name, "parameters": parameters}, ensure_ascii=False)


# ── normalize_tool_name ────────────────────────────────────────────────────────


class TestNormalizeToolName:
    def test_snake_case_unchanged(self):
        assert normalize_tool_name("search_loan_rate") == "search_loan_rate"

    def test_camel_case(self):
        assert normalize_tool_name("searchLoanRate") == "search_loan_rate"

    def test_pascal_case(self):
        assert normalize_tool_name("SearchLoanRate") == "search_loan_rate"

    def test_kebab_case(self):
        assert normalize_tool_name("search-loan-rate") == "search_loan_rate"

    def test_all_caps_acronym(self):
        assert normalize_tool_name("getHTTPSConfig") == "get_https_config"

    def test_leading_trailing_spaces(self):
        assert normalize_tool_name("  search_loan_rate  ") == "search_loan_rate"


# ── try_parse_json ─────────────────────────────────────────────────────────────


class TestTryParseJson:
    def test_valid_json(self):
        raw = '{"tool_name": "foo", "parameters": {}}'
        result = try_parse_json(raw)
        assert result == {"tool_name": "foo", "parameters": {}}

    def test_markdown_code_block_json(self):
        raw = '```json\n{"tool_name": "foo", "parameters": {}}\n```'
        result = try_parse_json(raw)
        assert result is not None
        assert result["tool_name"] == "foo"

    def test_markdown_code_block_no_lang(self):
        raw = '```\n{"tool_name": "bar"}\n```'
        result = try_parse_json(raw)
        assert result is not None
        assert result["tool_name"] == "bar"

    def test_invalid_json_returns_none(self):
        assert try_parse_json("not a json string") is None

    def test_empty_string_returns_none(self):
        assert try_parse_json("") is None


# ── compare_parameters ─────────────────────────────────────────────────────────


class TestCompareParameters:
    def test_exact_match(self):
        match, missing, extra = compare_parameters(
            {"loan_type": "personal", "amount": 5000000},
            {"loan_type": "personal", "amount": 5000000},
        )
        assert match is True
        assert missing == []
        assert extra == []

    def test_type_cast_int_str(self):
        """정수 5000000 과 문자열 "5000000" 을 동일하게 처리."""
        match, missing, extra = compare_parameters(
            {"amount": "5000000"},
            {"amount": 5000000},
        )
        assert match is True

    def test_type_cast_str_int(self):
        match, missing, extra = compare_parameters(
            {"amount": 720},
            {"amount": "720"},
        )
        assert match is True

    def test_missing_param(self):
        match, missing, extra = compare_parameters(
            {"loan_type": "personal"},           # amount 누락
            {"loan_type": "personal", "amount": 5000000},
        )
        assert match is False
        assert "amount" in missing

    def test_extra_param(self):
        match, missing, extra = compare_parameters(
            {"loan_type": "personal", "amount": 5000000, "currency": "KRW"},  # currency 추가
            {"loan_type": "personal", "amount": 5000000},
        )
        assert match is False
        assert "currency" in extra

    def test_value_mismatch(self):
        match, missing, extra = compare_parameters(
            {"loan_type": "business"},  # "personal" 이어야 함
            {"loan_type": "personal"},
        )
        assert match is False
        assert missing == []
        assert extra == []

    def test_empty_both(self):
        match, missing, extra = compare_parameters({}, {})
        assert match is True


# ── evaluate_single_call ───────────────────────────────────────────────────────


class TestEvaluateSingleCall:
    def _call(self, raw: str, expected: dict = EXPECTED_CALL) -> dict:
        return evaluate_single_call(expected, raw, SCENARIO_ID, TURN_INDEX, MODEL_NAME)

    # 정상 케이스
    def test_perfect_match(self):
        raw = _raw("search_loan_rate", {"loan_type": "personal", "amount": 5000000})
        result = self._call(raw)
        assert result["call_score"] == 1
        assert result["call_correct"] is True
        assert result["params_match"] is True
        assert result["reason"] == "정확"
        assert result["_parse_failed"] is False

    # snake_case 정규화
    def test_camel_case_tool_name_accepted(self):
        raw = _raw("searchLoanRate", {"loan_type": "personal", "amount": 5000000})
        result = self._call(raw)
        assert result["call_correct"] is True
        assert result["call_score"] == 1

    def test_pascal_case_tool_name_accepted(self):
        raw = _raw("SearchLoanRate", {"loan_type": "personal", "amount": 5000000})
        result = self._call(raw)
        assert result["call_correct"] is True

    # 타입 캐스팅
    def test_string_int_type_cast(self):
        raw = _raw("search_loan_rate", {"loan_type": "personal", "amount": "5000000"})
        result = self._call(raw)
        assert result["params_match"] is True
        assert result["call_score"] == 1

    # Tool 이름 불일치
    def test_wrong_tool_name(self):
        raw = _raw("get_exchange_rate", {"loan_type": "personal", "amount": 5000000})
        result = self._call(raw)
        assert result["call_correct"] is False
        assert result["call_score"] == 0
        assert "불일치" in result["reason"]

    # 파라미터 누락
    def test_missing_parameter(self):
        raw = _raw("search_loan_rate", {"loan_type": "personal"})  # amount 없음
        result = self._call(raw)
        assert result["params_match"] is False
        assert "amount" in result["missing_params"]
        assert result["call_score"] == 0

    # 불필요 파라미터
    def test_extra_parameter(self):
        raw = _raw("search_loan_rate", {"loan_type": "personal", "amount": 5000000, "currency": "KRW"})
        result = self._call(raw)
        assert result["params_match"] is False
        assert "currency" in result["extra_params"]
        assert result["call_score"] == 0

    # JSON 파싱 실패
    def test_invalid_json_parse_failed(self):
        result = self._call("이건 JSON이 아닙니다")
        assert result["_parse_failed"] is True
        assert result["call_score"] == 0
        assert result["tool_name_extracted"] is None
        assert result["params_extracted"] is None
        assert result["reason"] == "JSON 파싱 실패"

    def test_markdown_wrapped_json_parsed(self):
        inner = json.dumps({"tool_name": "search_loan_rate", "parameters": {"loan_type": "personal", "amount": 5000000}})
        raw = f"```json\n{inner}\n```"
        result = self._call(raw)
        assert result["_parse_failed"] is False
        assert result["call_score"] == 1

    # 메타데이터 필드 검증
    def test_metadata_fields(self):
        raw = _raw("search_loan_rate", {"loan_type": "personal", "amount": 5000000})
        result = self._call(raw)
        assert result["scenario_id"] == SCENARIO_ID
        assert result["turn_index"] == TURN_INDEX
        assert result["model_name"] == MODEL_NAME
        assert result["slot_score"] is None
        assert result["relevance_score"] is None
        assert result["completion_score"] is None

    # 파싱 실패 시 missing_params는 expected 키 전체
    def test_parse_failed_missing_params_contains_all_expected(self):
        result = self._call("garbage")
        assert set(result["missing_params"]) == set(EXPECTED_CALL["parameters"].keys())
