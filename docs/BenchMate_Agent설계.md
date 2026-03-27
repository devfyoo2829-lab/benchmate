# Agent 설계서

# BenchMate — Agent 설계 문서

## Agent Design Document

*작성일: 2026.03 | 작성자: 곽승연 | 상위 문서: BenchMate 기획서 최종연관 문서: 데이터 구조 설계 문서 v1.1, 데이터 요구사항 문서*

---

## 문서 목적

BenchMate LangGraph 파이프라인을 구성하는 에이전트의 전체 구조를 정의한다.
각 노드의 책임·입력·출력·처리 로직, 분기 조건, 재시도 로직, Multi-turn 루프 설계를 포함한다.
Claude Code로 개발 착수 시 이 문서를 노드 구현의 직접적인 기준으로 사용한다.

---

## 목차

1. 에이전트 구성 개요
2. 전체 그래프 구조 (graph.py)
3. 노드 정의 (10개 노드)
4. 분기 로직
5. 재시도 로직
6. Multi-turn 루프 설계
7. 오류 처리 정책
8. 노드 구현 순서 (개발 우선순위)

---

## 1. 에이전트 구성 개요

### 1.1 아키텍처 선택: 단일 에이전트 + 조건부 분기

BenchMate는 하나의 LangGraph StateGraph로 구성된 단일 파이프라인 에이전트다.
복잡한 멀티 에이전트 오케스트레이션 대신, `route_mode` 노드의 조건부 분기로
Knowledge 경로와 Agent 경로를 분리한다.

**선택 근거**

- 평가 파이프라인은 순차적 처리가 명확하므로 단일 그래프로 충분
- EvalState가 모든 중간 결과를 담으므로 에이전트 간 통신 불필요
- LangSmith 추적이 단일 그래프에서 더 명확하게 가시화됨

### 1.2 노드 목록 및 파일 경로

| 순서 | 노드 이름 | 파일 경로  | 역할 요약 |
| --- | --- | --- | --- |
| 1 | `load_scenarios` | `/pipeline/nodes/load_scenarios.py` | JSON 파일 로드 → EvalState 초기화 |
| 2 | `route_mode` | `/pipeline/nodes/route_mode.py` | eval_mode에 따라 Knowledge / Agent 분기 |
| 3a | `generate_responses` | `/pipeline/nodes/generate_responses.py` | Knowledge 문항에 대한 멀티 모델 응답 수집 |
| 3b | `generate_tool_calls` | `/pipeline/nodes/generate_tool_calls.py` | Agent 시나리오에 대한 Tool 호출 응답 수집 |
| 4a | `judge_knowledge` | `/pipeline/nodes/judge_knowledge.py` | Qwen Judge로 Knowledge 채점 (A→B, B→A) |
| 4b | `evaluate_call` | `/pipeline/nodes/evaluate_call.py` | call 항목 코드 기반 JSON 비교 채점 |
| 4c | `judge_agent` | `/pipeline/nodes/judge_agent.py` | slot / relevance / completion Judge 채점 |
| 5 | `validate_scores` | `/pipeline/nodes/validate_scores.py` | Judge 출력 JSON 파싱 검증 · 재시도 분기 |
| 6 | `flag_human_review` | `/pipeline/nodes/flag_human_review.py` | 선별 기준에 따른 Human Review 큐 구성 |
| 7 | `aggregate_results` | `/pipeline/nodes/aggregate_results.py` | summary_table, judge_reliability, 비용 계산 |
| 8 | `generate_report` | `/pipeline/nodes/generate_report.py` | PM 해석 리포트 생성 · 세션 JSON 저장 |

---

## 2. 전체 그래프 구조 (graph.py)

```python
# /pipeline/graph.py

from langgraph.graph import StateGraph, END
from pipeline.state import EvalState
from pipeline.nodes.load_scenarios import load_scenarios
from pipeline.nodes.route_mode import route_mode
from pipeline.nodes.generate_responses import generate_responses
from pipeline.nodes.generate_tool_calls import generate_tool_calls
from pipeline.nodes.judge_knowledge import judge_knowledge
from pipeline.nodes.evaluate_call import evaluate_call
from pipeline.nodes.judge_agent import judge_agent
from pipeline.nodes.validate_scores import validate_scores
from pipeline.nodes.flag_human_review import flag_human_review
from pipeline.nodes.aggregate_results import aggregate_results
from pipeline.nodes.generate_report import generate_report

def build_graph() -> StateGraph:
    graph = StateGraph(EvalState)

    # ── 노드 등록 ──────────────────────────────────────
    graph.add_node("load_scenarios", load_scenarios)
    graph.add_node("route_mode", route_mode)
    graph.add_node("generate_responses", generate_responses)
    graph.add_node("generate_tool_calls", generate_tool_calls)
    graph.add_node("judge_knowledge", judge_knowledge)
    graph.add_node("evaluate_call", evaluate_call)
    graph.add_node("judge_agent", judge_agent)
    graph.add_node("validate_scores", validate_scores)
    graph.add_node("flag_human_review", flag_human_review)
    graph.add_node("aggregate_results", aggregate_results)
    graph.add_node("generate_report", generate_report)

    # ── 엣지 정의 ──────────────────────────────────────
    graph.set_entry_point("load_scenarios")
    graph.add_edge("load_scenarios", "route_mode")

    # route_mode 조건부 분기
    graph.add_conditional_edges(
        "route_mode",
        decide_branch,
        {
            "knowledge": "generate_responses",
            "agent":     "generate_tool_calls",
            "integrated_k": "generate_responses",  # integrated는 knowledge 먼저
        }
    )

    # Knowledge 경로
    graph.add_edge("generate_responses", "judge_knowledge")
    graph.add_edge("judge_knowledge", "validate_scores")

    # Agent 경로
    graph.add_edge("generate_tool_calls", "evaluate_call")
    graph.add_edge("evaluate_call", "judge_agent")
    graph.add_edge("judge_agent", "validate_scores")

    # validate_scores 재시도 분기
    graph.add_conditional_edges(
        "validate_scores",
        decide_retry,
        {
            "retry_knowledge": "judge_knowledge",
            "retry_agent":     "judge_agent",
            "ok":              "flag_human_review",
        }
    )

    # 하류 공통 경로
    graph.add_edge("flag_human_review", "aggregate_results")
    graph.add_edge("aggregate_results", "generate_report")
    graph.add_edge("generate_report", END)

    return graph.compile()
```

### 분기 함수 시그니처

```python
def decide_branch(state: EvalState) -> str:
    """route_mode 노드 이후 분기 결정"""
    mode = state["eval_mode"]
    if mode == "knowledge":
        return "knowledge"
    elif mode == "agent":
        return "agent"
    else:  # integrated — knowledge 먼저 실행
        return "integrated_k"

def decide_retry(state: EvalState) -> str:
    """validate_scores 노드 이후 재시도 또는 진행 결정"""
    if state["retry_count"] > 0:
        # 어떤 브랜치를 재시도할지 last_failed_branch 필드로 판단
        if state.get("last_failed_branch") == "knowledge":
            return "retry_knowledge"
        elif state.get("last_failed_branch") == "agent":
            return "retry_agent"
    return "ok"
```

---

## 3. 노드 정의

각 노드는 `(state: EvalState) -> dict` 시그니처를 따른다.
반환값은 EvalState 중 변경된 필드만 포함하는 부분 딕셔너리다.

---

### Node 1. `load_scenarios`

**책임**: 도메인 JSON 파일을 읽어 EvalState의 초기 데이터를 세팅한다.

**입력**: `eval_mode`, `domain`, `selected_models` (사용자가 UI에서 설정한 값)

**처리**:

1. `/data/questions/{domain}.json` 로드 → `questions`
2. `/data/tools/{domain}_tools.json` 로드 → `available_tools`
3. `/data/scenarios/{domain}_scenarios.json` 로드 → `scenarios`
4. `/prompts/knowledge_judge_template.txt` 로드 → `rubric_text`
5. `eval_session_id` 생성 (`eval_` + 현재 타임스탬프)
6. `retry_count = 0` 초기화

**출력**:

```python
{
    "questions": List[QuestionItem],
    "available_tools": List[ToolDefinition],
    "scenarios": List[ScenarioItem],
    "rubric_text": str,
    "eval_session_id": str,
    "retry_count": 0,
    "knowledge_scores_ab": [],
    "knowledge_scores_ba": [],
    "knowledge_scores_final": [],
    "agent_scores": [],
    "model_responses": [],
    "human_review_queue": [],
}
```

**예외 처리**: JSON 파일 없거나 파싱 실패 시 FileNotFoundError 발생 → Streamlit에서 사용자 알림 표시

---

### Node 2. `route_mode`

**책임**: `eval_mode` 값을 읽어 다음 노드를 결정하는 라우터 역할.
실제 처리는 없고 `decide_branch` 함수에서 분기 결정.

**입력**: `eval_mode`

**처리**: EvalState 변경 없음. `decide_branch` 반환값만 그래프 라우팅에 사용.

**출력**: `{}` (변경 없음)

---

### Node 3a. `generate_responses`

**책임**: Knowledge 문항 목록에 대해 선택된 모든 모델을 비동기 병렬 호출하여 응답을 수집한다.

**입력**: `questions`, `selected_models`, `available_tools`

**처리**:

```python
import asyncio

async def call_model(model_name: str, question: QuestionItem) -> ModelResponse:
    """단일 모델 단일 문항 호출"""
    system_prompt = f"당신은 {question['domain']} 도메인 전문가입니다. 질문에 정확하고 자연스러운 한국어로 답변하세요."
    # 모델별 API 클라이언트 분기 (OpenAI / Anthropic / Upstage SDK)
    start = time.time()
    try:
        response = await api_client.chat(model_name, system_prompt, question["question"])
        return ModelResponse(
            model_name=model_name,
            item_id=question["id"],
            response_text=response.text,
            tool_call_output=None,
            raw_output=None,
            latency_ms=int((time.time() - start) * 1000),
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            status="success",
        )
    except Exception:
        return ModelResponse(..., status="retry")

# 모든 (모델, 문항) 조합을 병렬 실행
tasks = [call_model(m, q) for m in state["selected_models"] for q in state["questions"]]
results = await asyncio.gather(*tasks)
```

**출력**:

```python
{"model_responses": List[ModelResponse]}
```

**재시도**: status="retry"인 항목은 최대 3회 재시도. 3회 초과 시 status="failed"로 기록하고 해당 모델 제외 알림.

---

### Node 3b. `generate_tool_calls`

**책임**: Agent 시나리오에 대해 모든 모델을 호출하여 Tool 호출 응답(JSON)을 수집한다.

**입력**: `scenarios`, `selected_models`, `available_tools`

**처리**:

```python
# 시스템 프롬프트에 사용 가능한 Tool 목록과 출력 형식 명시
TOOL_SYSTEM_PROMPT = """
당신은 기업 업무를 처리하는 AI Agent입니다.
사용자 요청을 분석하고, 아래 도구 중 적합한 것을 선택해 호출하세요.

사용 가능한 도구:
{tool_definitions}

반드시 아래 JSON 형식으로만 응답하세요. 다른 텍스트는 출력하지 마세요.
{{
  "tool_name": "<도구 이름>",
  "parameters": {{<파라미터 키-값>}}
}}

적합한 도구가 없거나 정보가 부족하면:
- 정보 부족: {{"action": "ask", "message": "<필요한 정보 요청>"}}
- 불가능한 요청: {{"action": "reject", "message": "<거절 이유>"}}
"""

# Single-turn: 단일 턴 호출
# Multi-turn: turns 배열을 순서대로 실행하며 이전 tool_result를 컨텍스트에 포함
```

**Multi-turn 처리**:

```python
async def run_multi_turn(model_name: str, scenario: ScenarioItem) -> List[ModelResponse]:
    conversation_history = []
    responses = []

    for turn in scenario["turns"]:
        if turn["role"] == "user":
            conversation_history.append({"role": "user", "content": turn["content"]})
            raw = await call_tool_model(model_name, conversation_history, scenario["available_tools"])
            responses.append(ModelResponse(
                item_id=scenario["id"],
                turn_index=turn["turn_index"],
                raw_output=raw,
                tool_call_output=try_parse_json(raw),
                ...
            ))
            conversation_history.append({"role": "assistant", "content": raw})

        elif turn["role"] == "tool_result":
            # Mock 반환값 주입: 실제 Tool 실행 없이 scenario JSON에 정의된 값 사용
            conversation_history.append({"role": "tool", "content": turn["content"]})

    return responses
```

**출력**:

```python
{"model_responses": state["model_responses"] + new_responses}
```

---

### Node 4a. `judge_knowledge`

**책임**: Qwen 2.5 Judge를 사용해 Knowledge 응답을 채점한다.
Position Bias 제거를 위해 A→B(ab), B→A(ba) 두 방향으로 교차 채점한다.

**입력**: `questions`, `model_responses`, `rubric_text`

**처리**:

```python
# 두 모델씩 짝지어 교차 채점
# judge_order="ab": response_A를 먼저 제시 후 response_B
# judge_order="ba": response_B를 먼저 제시 후 response_A

def build_judge_prompt(question, ref_answer, instance_rubric, model_response, judge_order):
    """knowledge_judge_template.txt 렌더링"""
    template = jinja_env.get_template("knowledge_judge_template.txt")
    return template.render(
        domain_name=DOMAIN_NAMES[question["domain"]],
        question=question["question"],
        reference_answer=ref_answer,
        instance_rubric=question["instance_rubric"],
        model_response=model_response,
        judge_order=judge_order,
    )

# Qwen 2.5 호출 (HuggingFace Inference API 또는 로컬)
# temperature=0.0, max_tokens=512
```

**출력**:

```python
{
    "knowledge_scores_ab": List[KnowledgeScore],  # judge_order="ab"
    "knowledge_scores_ba": List[KnowledgeScore],  # judge_order="ba"
}
```

**주의**: 파싱 실패한 raw_output은 버리지 않고 별도 리스트에 보관 → `validate_scores`로 전달.

---

### Node 4b. `evaluate_call`

**책임**: Agent 시나리오의 call 항목을 LLM 없이 코드로 채점한다.
Tool 이름과 파라미터를 JSON 파싱 후 정답과 직접 비교한다.

**입력**: `scenarios`, `model_responses`

**처리**:

```python
def evaluate_single_call(
    expected: Dict,       # scenario의 expected_tool_calls[turn_index]
    raw_output: str,      # 모델이 생성한 원본 문자열
) -> AgentScore:

    # 1. JSON 파싱 시도
    try:
        parsed = json.loads(raw_output)
    except json.JSONDecodeError:
        # 파싱 실패: 마크다운 코드블록 제거 후 재시도
        cleaned = re.sub(r"```json|```", "", raw_output).strip()
        try:
            parsed = json.loads(cleaned)
        except:
            return AgentScore(
                call_correct=False, params_match=False,
                call_score=0,
                tool_name_extracted=None, params_extracted=None,
                missing_params=[], extra_params=[],
                reason="JSON 파싱 실패",
                ...
            )

    # 2. Tool 이름 추출 및 정규화
    extracted_name = parsed.get("tool_name", "")
    expected_name = expected["tool_name"]
    # snake_case 정규화: camelCase, PascalCase → snake_case
    name_match = normalize(extracted_name) == normalize(expected_name)

    # 3. 파라미터 비교
    extracted_params = parsed.get("parameters", {})
    expected_params = expected["parameters"]

    missing = [k for k in expected_params if k not in extracted_params]
    extra = [k for k in extracted_params if k not in expected_params]

    # 값 비교: 타입 캐스팅 허용 ("720" == 720 → True)
    value_match = all(
        str(extracted_params.get(k)) == str(v)
        for k, v in expected_params.items()
        if k in extracted_params
    )
    params_match = (len(missing) == 0 and len(extra) == 0 and value_match)

    call_score = 1 if (name_match and params_match) else 0

    return AgentScore(
        tool_name_extracted=extracted_name,
        params_extracted=extracted_params,
        call_correct=name_match,
        params_match=params_match,
        missing_params=missing,
        extra_params=extra,
        call_score=call_score,
        slot_score=None,
        relevance_score=None,
        completion_score=None,
        reason=f"{'정확' if call_score == 1 else f'불일치: tool={extracted_name}, missing={missing}'}",
        ...
    )
```

**출력**:

```python
{"agent_scores": List[AgentScore]}  # call 항목만 채점. slot/relevance/completion은 None
```

---

### Node 4c. `judge_agent`

**책임**: call 외 나머지 3개 항목(slot, relevance, completion)을 Qwen Judge로 채점한다.
시나리오 유형에 따라 해당 항목만 선택적으로 채점한다.

**입력**: `scenarios`, `model_responses`, `agent_scores`

**적용 기준**:

| 시나리오 유형 | slot | relevance | completion |
| --- | --- | --- | --- |
| single_A (정상 호출) | ✗ | ✗ | 마지막 턴에 ✅ |
| single_B (정보 부족) | ✅ | ✗ | ✗ |
| single_C (불가능 요청) | ✗ | ✅ | ✗ |
| multi (5턴 체인) | 해당 턴에 ✅ | 해당 턴에 ✅ | completion 턴에 ✅ |

**처리**:

```python
def get_eval_type(scenario: ScenarioItem, turn_index: int) -> Optional[str]:
    """시나리오 유형과 턴 인덱스에 따라 채점 항목 결정"""
    stype = scenario["scenario_type"]
    if stype == "single_B":
        return "slot"
    elif stype == "single_C":
        return "relevance"
    elif stype == "single_A":
        return "completion"  # 단일 턴에서 Tool 결과 요약
    elif stype == "multi":
        # turns 배열에서 해당 턴의 role 확인
        turn = scenario["turns"][turn_index]
        if turn.get("expects") == "slot":
            return "slot"
        elif turn.get("expects") == "rejection":
            return "relevance"
        elif turn.get("expects") == "completion":
            return "completion"
    return None

# agent_judge_template.txt 렌더링 후 Qwen 2.5 호출
# 반환: {"score": int, "reason": str}
# slot/relevance: score 0 or 1
# completion: score 1~3
```

**출력**:

```python
{"agent_scores": updated_agent_scores}  # slot_score/relevance_score/completion_score 채워진 버전
```

---

### Node 5. `validate_scores`

**책임**: Judge 출력이 올바른 JSON으로 파싱됐는지 검증한다.
파싱 실패 항목이 있으면 `retry_count`를 올리고 재시도 분기로 보낸다.

**입력**: `knowledge_scores_ab`, `knowledge_scores_ba`, `agent_scores`, `retry_count`

**처리**:

```python
def validate_scores(state: EvalState) -> dict:
    failed_knowledge = [s for s in state["knowledge_scores_ab"] if s.get("_parse_failed")]
    failed_agent = [s for s in state["agent_scores"] if s.get("_parse_failed")]

    if (failed_knowledge or failed_agent) and state["retry_count"] < 3:
        return {
            "retry_count": state["retry_count"] + 1,
            "last_failed_branch": "knowledge" if failed_knowledge else "agent",
            "_retry_targets": failed_knowledge + failed_agent,
        }

    # 최대 재시도 초과 시 해당 항목을 Human Review 큐에 강제 포함
    if failed_knowledge or failed_agent:
        forced_reviews = [
            HumanReviewItem(
                item_id=s["question_id"],
                item_type="knowledge",
                review_reason="Judge JSON 파싱 3회 실패",
                is_reviewed=False,
                ...
            )
            for s in failed_knowledge + failed_agent
        ]
        return {
            "human_review_queue": state["human_review_queue"] + forced_reviews,
            "retry_count": 0,
            "last_failed_branch": None,
        }

    return {"retry_count": 0, "last_failed_branch": None}
```

**분기 조건 (`decide_retry`)**:

- `retry_count > 0` AND `last_failed_branch == "knowledge"` → `judge_knowledge`로 복귀
- `retry_count > 0` AND `last_failed_branch == "agent"` → `judge_agent`로 복귀
- 그 외 → `flag_human_review`로 진행

---

### Node 6. `flag_human_review`

**책임**: 선별 기준을 충족하는 항목을 Human Review 큐에 추가한다.

**입력**: `knowledge_scores_ab`, `knowledge_scores_ba`, `agent_scores`

**선별 기준 (OR 조건)**:

```python
def should_flag(ab: KnowledgeScore, ba: KnowledgeScore) -> tuple[bool, str]:
    """Knowledge 항목 선별 — 4가지 OR 조건"""

    # 1. 교차 평가 편차 ≥ 3점
    if abs(ab["total"] - ba["total"]) >= 3:
        return True, f"교차 편차 {abs(ab['total'] - ba['total'])}점"

    # 2. 할루시네이션 위험
    if ab["hallucination"] <= 2 or ba["hallucination"] <= 2:
        return True, f"hallucination 점수 낮음"

    # 3. 랜덤 20% 샘플
    if random.random() < 0.20:
        return True, "랜덤 품질 샘플"

    return False, ""

def should_flag_agent(score: AgentScore) -> tuple[bool, str]:
    """Agent 항목 선별"""
    if score["call_score"] == 0:
        return True, "Tool 호출 실패"
    if random.random() < 0.20:
        return True, "랜덤 품질 샘플"
    return False, ""
```

**출력**:

```python
{"human_review_queue": List[HumanReviewItem]}
```

---

### Node 7. `aggregate_results`

**책임**: 전체 채점 결과를 집계하여 summary_table, judge_reliability, estimated_cost를 생성한다.

**입력**: `knowledge_scores_final`, `agent_scores`, `human_review_queue`, `selected_models`

**처리**:

```python
# 1. Knowledge 최종 점수 계산 (Position Bias 평균)
def compute_final_knowledge_scores(ab_list, ba_list) -> List[KnowledgeScore]:
    final = []
    for ab in ab_list:
        ba = find_matching(ba_list, ab["question_id"], ab["model_name"])
        if not ba:
            continue
        final.append(KnowledgeScore(
            question_id=ab["question_id"],
            model_name=ab["model_name"],
            accuracy=(ab["accuracy"] + ba["accuracy"]) / 2,
            fluency=(ab["fluency"] + ba["fluency"]) / 2,
            hallucination=(ab["hallucination"] + ba["hallucination"]) / 2,
            domain_expertise=(ab["domain_expertise"] + ba["domain_expertise"]) / 2,
            utility=(ab["utility"] + ba["utility"]) / 2,
            total=sum([...]) / 2,
            judge_order="final",
            reason="ab/ba 평균",
        ))
    return final

# 2. summary_table: 모델 × 기준 집계
# {model_name: {knowledge_total, accuracy, ..., call_score, slot_score, ...}}

# 3. judge_reliability: Human Review 완료 항목 기준
#    Judge total과 Human total의 차이 ±2 이내 → 일치
reviewed = [r for r in state["human_review_queue"] if r["is_reviewed"]]
if reviewed:
    agreed = sum(
        1 for r in reviewed
        if abs(sum(r["judge_score"].values()) - sum(r["human_score"].values())) <= 2
    )
    judge_reliability = (agreed / len(reviewed)) * 100
else:
    judge_reliability = None

# 4. estimated_cost
# model_responses의 input_tokens, output_tokens × pricing.json 단가
```

**출력**:

```python
{
    "knowledge_scores_final": List[KnowledgeScore],
    "summary_table": Dict,
    "judge_reliability": Optional[float],
    "estimated_cost": Dict,
}
```

---

### Node 8. `generate_report`

**책임**: summary_table을 기반으로 PM 해석 리포트를 생성하고, 세션 JSON을 파일로 저장한다.

**입력**: `summary_table`, `judge_reliability`, `estimated_cost`, `eval_session_id`, `eval_mode`, `domain`

**처리**:

```python
# PM 리포트 생성 프롬프트 (Qwen 2.5 또는 GPT-4o)
REPORT_PROMPT = """
다음 LLM 평가 결과를 바탕으로 기업 실무 담당자를 위한 PM 해석 리포트를 작성하세요.

평가 요약:
- 평가 모드: {eval_mode}
- 도메인: {domain}
- 평가 모델: {models}
- Judge 신뢰도: {judge_reliability}%

점수 테이블:
{summary_table_str}

리포트 구성:
1. 평가 요약 (1~2문장)
2. 종합 추천 모델 및 핵심 근거
3. Knowledge vs Agent 괴리 분석
   - 지식 점수는 높지만 Tool calling이 약한 모델 식별
   - "A 모델은 ~~에 적합하고 ~~에는 부적합합니다" 형식
4. 도메인별 강점 모델
5. 고위험 항목 경고 (hallucination 낮음 / call 실패율 높음)
6. 비용 대비 성능 분석
7. 도입 우선순위 제안 3가지
"""

# 세션 JSON 저장
session_data = {
    "session_id": state["eval_session_id"],
    "eval_mode": state["eval_mode"],
    "domain": state["domain"],
    "selected_models": state["selected_models"],
    "summary_table": state["summary_table"],
    "pm_report_text": report_text,
    "judge_reliability": state["judge_reliability"],
    "created_at": datetime.now(timezone(timedelta(hours=9))).isoformat(),
}
with open(f"/output/{state['eval_session_id']}.json", "w", encoding="utf-8") as f:
    json.dump(session_data, f, ensure_ascii=False, indent=2)
```

**출력**:

```python
{"pm_report_text": str}
```

---

## 4. 분기 로직

### 4.1 `route_mode` 분기

```
eval_mode = "knowledge"   → generate_responses
eval_mode = "agent"       → generate_tool_calls
eval_mode = "integrated"  → generate_responses (Knowledge 먼저 실행)
                            generate_responses 완료 후 → generate_tool_calls
```

**integrated 모드 처리 방식**:
integrated 모드는 Knowledge → Agent 순서로 두 번 파이프라인을 통과한다.
EvalState에 `_integrated_phase: "knowledge" | "agent"` 필드를 추가해 현재 단계를 추적한다.
Knowledge 파이프라인 완료 후 `generate_tool_calls`로 분기, Agent 파이프라인을 이어서 실행한다.

```python
# route_mode 수정 버전 (integrated 처리)
def decide_branch(state: EvalState) -> str:
    mode = state["eval_mode"]
    phase = state.get("_integrated_phase", "knowledge")

    if mode == "knowledge":
        return "knowledge"
    elif mode == "agent":
        return "agent"
    elif mode == "integrated" and phase == "knowledge":
        return "integrated_k"
    elif mode == "integrated" and phase == "agent":
        return "agent"
```

### 4.2 `validate_scores` 분기

```
파싱 실패 있음 + retry_count < 3
    → last_failed_branch == "knowledge" → judge_knowledge
    → last_failed_branch == "agent"     → judge_agent

파싱 실패 있음 + retry_count ≥ 3
    → 해당 항목 Human Review 큐 강제 포함
    → flag_human_review

파싱 실패 없음
    → flag_human_review
```

---

## 5. 재시도 로직

### 5.1 LLM API 호출 재시도 (`generate_responses`, `generate_tool_calls`)

```python
async def call_with_retry(call_fn, max_retries=3, backoff=2.0):
    for attempt in range(max_retries):
        try:
            return await call_fn()
        except (APIError, TimeoutError, RateLimitError) as e:
            if attempt == max_retries - 1:
                raise
            await asyncio.sleep(backoff * (2 ** attempt))  # 지수 백오프
    raise RuntimeError("최대 재시도 초과")
```

- 최대 재시도: 3회
- 백오프: 2초 → 4초 → 8초 (지수 백오프)
- 3회 초과 시: `status="failed"`, 해당 모델 결과 제외, Streamlit 알림

### 5.2 Judge JSON 파싱 재시도 (`validate_scores` → `judge_knowledge` / `judge_agent`)

```
재시도 1회차: 동일 프롬프트로 재호출 (Judge의 일시적 출력 오류 가능성)
재시도 2회차: 프롬프트 끝에 "반드시 JSON만 출력하세요. 다른 텍스트 금지." 추가
재시도 3회차: temperature를 0.0으로 명시적 설정 후 재호출
3회 모두 실패: Human Review 큐 강제 등록, _parse_failed=True로 마킹
```

### 5.3 재시도 상태 관리

```python
# EvalState에 추가 필드
"retry_count": int          # 현재 재시도 횟수 (최대 3)
"last_failed_branch": str   # "knowledge" | "agent" | None
"_retry_targets": List      # 재시도 대상 항목 ID 목록
```

---

## 6. Multi-turn 루프 설계

### 6.1 턴 실행 구조

Multi-turn 시나리오는 `generate_tool_calls` 노드 내부에서 처리된다.
LangGraph 레벨의 루프가 아닌 노드 내부의 Python for 루프로 구현한다.

```python
# 턴별 실행 흐름
for turn in scenario["turns"]:
    if turn["role"] == "user":
        # LLM 호출 → Tool 호출 생성
        model_output = await call_tool_model(conversation_history)
        conversation_history.append({"role": "assistant", "content": model_output})

    elif turn["role"] == "tool_result":
        # Mock 반환값 주입 (실제 API 호출 없음)
        conversation_history.append({
            "role": "tool",
            "content": turn["content"]  # scenario JSON에 사전 정의된 값
        })
```

### 6.2 맥락 의존성 검증

`context_dependency` 배열을 기반으로 LLM이 이전 턴의 값을 올바르게 활용했는지 검증한다.

```python
def check_context_retention(
    dep: ContextDependency,
    responses: List[ModelResponse],
) -> bool:
    """
    context_dependency 예시:
    from_turn=1, to_turn=2, carried_value="annual_rate"
    → Turn 1의 tool_result에서 "annual_rate": 4.7 확인
    → Turn 2의 tool_call_output parameters에 "annual_rate": 4.7 포함 여부 확인
    """
    # Turn 1 tool_result에서 carried_value 값 추출
    source_turn = next(r for r in responses if r["turn_index"] == dep["from_turn"])
    source_value = extract_value(source_turn["content"], dep["carried_value"])

    # Turn 2 tool_call_output에서 동일 값 확인
    target_turn = next(r for r in responses if r["turn_index"] == dep["to_turn"])
    target_params = target_turn.get("params_extracted", {})
    actual_value = target_params.get(dep["carried_value"])

    return str(source_value) == str(actual_value)
```

맥락 의존성 검증 결과는 `AgentScore`의 별도 필드 `context_retained: Optional[bool]`에 기록한다.

### 6.3 Multi-turn 채점 항목 적용

| 턴 | 채점 항목 | 비고 |
| --- | --- | --- |
| 사용자 요청 → Tool 호출 발생 | call (코드) | turn["role"] == "user"이고 expected_tool_calls에 포함 |
| 정보 부족 → 되묻기 발생 | slot (Judge) | expected_tool_calls 없고 scenario에 되묻기 기대 |
| Tool result → 자연어 요약 | completion (Judge) | 마지막 user 턴 이후 응답 |
| 이전 값 활용 여부 | context_retention (코드) | context_dependency 정의된 턴 |

---

## 7. 오류 처리 정책

| 오류 유형 | 발생 노드 | 처리 방법 |
| --- | --- | --- |
| API 호출 실패 (3회 초과) | generate_responses, generate_tool_calls | 해당 모델 제외, Streamlit 경고 표시, 나머지 계속 진행 |
| Judge JSON 파싱 실패 (3회 초과) | validate_scores | Human Review 큐 강제 등록, 해당 항목 점수 None 처리 |
| Tool JSON 파싱 완전 실패 | evaluate_call | call_score=0, raw_output 보존, Human Review 큐 등록 |
| 도메인 JSON 파일 없음 | load_scenarios | FileNotFoundError 발생 → Streamlit에서 사용자 알림 후 중단 |
| 모델 선택 2개 미만 | Streamlit Screen 4 | 파이프라인 실행 전 차단 |
| integrated 모드 phase 오류 | route_mode | 기본값 "knowledge"로 폴백, 로그 경고 |

---

## 8. 노드 구현 순서 (개발 우선순위)

Claude Code로 개발할 때 아래 순서로 세션을 나눠 진행한다.

```
Phase 1 — 뼈대 (1~2일)
  세션 1: pipeline/state.py — EvalState 전체 TypedDict 구현
  세션 2: pipeline/graph.py — 노드 등록 + 엣지 연결 (노드 본체는 빈 함수로)
  세션 3: pipeline/nodes/load_scenarios.py — JSON 로드 + EvalState 초기화
  세션 4: evaluators/tool_call_evaluator.py — evaluate_call 핵심 로직 (독립 구현 후 단위 테스트)

Phase 2 — Knowledge 경로 (2~3일)
  세션 5: pipeline/nodes/generate_responses.py — 멀티 모델 비동기 호출
  세션 6: pipeline/nodes/judge_knowledge.py — Qwen Judge 호출 + Jinja2 템플릿 렌더링
  세션 7: pipeline/nodes/validate_scores.py — JSON 파싱 검증 + 재시도 분기
  세션 8: Knowledge End-to-End 파이프라인 테스트 (금융 문항 3개 × 2개 모델)

Phase 3 — Agent 경로 (2~3일)
  세션 9: pipeline/nodes/generate_tool_calls.py — Single-turn Tool 호출 수집
  세션 10: pipeline/nodes/evaluate_call.py — evaluate_call 노드 통합
  세션 11: pipeline/nodes/judge_agent.py — slot/relevance/completion Judge
  세션 12: Multi-turn 시나리오 1개 파일럿 테스트

Phase 4 — 하류 노드 (1~2일)
  세션 13: pipeline/nodes/flag_human_review.py — 선별 기준 4가지
  세션 14: pipeline/nodes/aggregate_results.py — summary_table + judge_reliability
  세션 15: pipeline/nodes/generate_report.py — PM 리포트 생성 + 세션 저장

Phase 5 — Streamlit UI (2~3일)
  세션 16~22: screen1~7.py 순서대로
```