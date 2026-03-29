"""
BenchMate — Node 1: load_scenarios

도메인 JSON 파일과 Judge 프롬프트 템플릿을 로드하여 EvalState를 초기화한다.

입력: eval_mode, domain, selected_models (UI에서 사용자가 설정)
출력: questions, available_tools, scenarios, rubric_text, eval_session_id,
      retry_count, 빈 리스트 필드들
"""

import json
import os
from datetime import datetime
from typing import List

from pipeline.state import (
    EvalState,
    QuestionItem,
    ScenarioItem,
    ToolDefinition,
)

# 프로젝트 루트 (pipeline/nodes/ 에서 두 단계 상위)
_ROOT = os.path.join(os.path.dirname(__file__), "..", "..")


def _load_json(path: str) -> object:
    """JSON 파일 로드. 파일 없으면 FileNotFoundError 발생."""
    abs_path = os.path.normpath(path)
    if not os.path.exists(abs_path):
        raise FileNotFoundError(f"필수 데이터 파일을 찾을 수 없습니다: {abs_path}")
    with open(abs_path, encoding="utf-8") as f:
        return json.load(f)


def _load_text(path: str) -> str:
    """텍스트 파일 로드. 파일 없으면 FileNotFoundError 발생."""
    abs_path = os.path.normpath(path)
    if not os.path.exists(abs_path):
        raise FileNotFoundError(f"필수 프롬프트 파일을 찾을 수 없습니다: {abs_path}")
    with open(abs_path, encoding="utf-8") as f:
        return f.read()


def load_scenarios(state: EvalState) -> dict:
    domain: str = state["domain"]

    questions_raw = _load_json(
        os.path.join(_ROOT, "data", "questions", f"{domain}.json")
    )
    questions: List[QuestionItem] = (
        questions_raw.get("questions", []) if isinstance(questions_raw, dict) else questions_raw
    )

    try:
        tools_raw = _load_json(
            os.path.join(_ROOT, "data", "tools", f"{domain}_tools.json")
        )
        available_tools: List[ToolDefinition] = (
            tools_raw.get("tools", []) if isinstance(tools_raw, dict) else tools_raw
        )
    except FileNotFoundError:
        available_tools = []

    try:
        scenarios_raw = _load_json(
            os.path.join(_ROOT, "data", "scenarios", f"{domain}_scenarios.json")
        )
        scenarios: List[ScenarioItem] = (
            scenarios_raw.get("scenarios", []) if isinstance(scenarios_raw, dict) else scenarios_raw
        )
    except FileNotFoundError:
        scenarios = []

    rubric_text: str = _load_text(
        os.path.join(_ROOT, "prompts", "knowledge_judge_template.txt")
    )

    eval_session_id = "eval_" + datetime.now().strftime("%Y%m%d_%H%M%S")

    return {
        "questions": questions,
        "available_tools": available_tools,
        "scenarios": scenarios,
        "rubric_text": rubric_text,
        "eval_session_id": eval_session_id,
        "retry_count": 0,
        "knowledge_scores_ab": [],
        "knowledge_scores_ba": [],
        "knowledge_scores_final": [],
        "agent_scores": [],
        "model_responses": [],
        "human_review_queue": [],
    }
