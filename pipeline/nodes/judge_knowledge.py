"""
Node 4a: judge_knowledge
Qwen 2.5-32B Judge를 사용해 Knowledge 응답을 교차 채점한다.
judge_order "ab" / "ba" 두 방향으로 채점하여 Position Bias를 제거한다.
설계 기준: docs/BenchMate_Agent설계.md — Node 4a
"""

import asyncio
import json
import os
import re
from pathlib import Path
from typing import List

from dotenv import load_dotenv
from jinja2 import Environment, FileSystemLoader

from pipeline.nodes._hf_error import translate_hf_error
from pipeline.state import EvalState, KnowledgeScore, ModelResponse, QuestionItem

load_dotenv()

DOMAIN_NAMES: dict[str, str] = {
    "finance": "금융",
    "legal": "법무",
    "hr": "인사",
    "cs": "고객서비스",
    "manufacturing": "제조",
}

_PROMPTS_DIR = Path(__file__).parent.parent.parent / "prompts"
_jinja_env = Environment(loader=FileSystemLoader(str(_PROMPTS_DIR)))


def _build_prompt(question: QuestionItem, model_response: str) -> str:
    template = _jinja_env.get_template("knowledge_judge_template.txt")
    return template.render(
        domain_name=DOMAIN_NAMES.get(question["domain"], question["domain"]),
        question=question["question"],
        reference_answer=question["reference_answer"],
        instance_rubric=question["instance_rubric"],
        model_response=model_response,
    )


def _parse_judge_output(raw: str) -> dict:
    """Judge 원본 응답에서 JSON 파싱. 실패 시 예외 발생."""
    cleaned = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        return json.loads(match.group())
    return json.loads(cleaned)


async def _call_qwen(prompt: str) -> str:
    """HuggingFace Inference API로 Qwen 2.5-32B-Instruct 호출."""
    from huggingface_hub import AsyncInferenceClient

    client = AsyncInferenceClient(
        model="Qwen/Qwen2.5-7B-Instruct",
        token=os.environ["HF_TOKEN"],
    )
    try:
        response = await client.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=512,
        )
        return response.choices[0].message.content or ""
    except Exception as e:
        mapped = translate_hf_error(e)
        raise (mapped or e) from e


async def _judge_single(
    question: QuestionItem,
    model_name: str,
    response_text: str,
    judge_order: str,
) -> KnowledgeScore:
    """단일 (question, model, judge_order) 조합에 대한 Judge 호출 및 파싱."""
    prompt = _build_prompt(question, response_text)
    raw = await _call_qwen(prompt)

    try:
        parsed = _parse_judge_output(raw)
        return KnowledgeScore(
            question_id=question["id"],
            model_name=model_name,
            accuracy=int(parsed["accuracy"]),
            fluency=int(parsed["fluency"]),
            hallucination=int(parsed["hallucination"]),
            domain_expertise=int(parsed["domain_expertise"]),
            utility=int(parsed["utility"]),
            total=int(parsed["total"]),
            reason=str(parsed["reason"]),
            judge_order=judge_order,
        )
    except Exception:
        # 파싱 실패: _parse_failed 마킹 + raw_output 보존 → validate_scores가 감지
        return {  # type: ignore[return-value]
            "question_id": question["id"],
            "model_name": model_name,
            "accuracy": 0,
            "fluency": 0,
            "hallucination": 0,
            "domain_expertise": 0,
            "utility": 0,
            "total": 0,
            "reason": "",
            "judge_order": judge_order,
            "_parse_failed": True,
            "_raw_output": raw,
        }


async def _gather_scores(
    questions: List[QuestionItem],
    model_responses: List[ModelResponse],
    judge_order: str,
) -> List[KnowledgeScore]:
    """questions × model_responses 전체를 비동기 병렬 채점."""
    q_map = {q["id"]: q for q in questions}
    tasks = [
        _judge_single(q_map[resp["item_id"]], resp["model_name"], resp["response_text"], judge_order)
        for resp in model_responses
        if resp["item_id"] in q_map and resp["status"] != "failed"
    ]
    return list(await asyncio.gather(*tasks))


async def _run_both_orders(
    questions: List[QuestionItem],
    model_responses: List[ModelResponse],
) -> tuple[List[KnowledgeScore], List[KnowledgeScore]]:
    """ab / ba 두 방향을 동시에 병렬 실행."""
    ab, ba = await asyncio.gather(
        _gather_scores(questions, model_responses, "ab"),
        _gather_scores(questions, model_responses, "ba"),
    )
    return ab, ba


def judge_knowledge(state: EvalState) -> dict:
    scores_ab, scores_ba = asyncio.run(
        _run_both_orders(state.get("questions", []), state.get("model_responses", []))
    )
    return {
        "knowledge_scores_ab": scores_ab,
        "knowledge_scores_ba": scores_ba,
    }
