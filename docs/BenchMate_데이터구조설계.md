# 데이터 구조 설계

# BenchMate — 데이터 구조 설계 문서

## Data Structure Design

*작성일: 2026.03 | 작성자: 곽승연 | 버전: v1.1 | 상위 문서: BenchMate 기획서 최종v1.1 변경: 데이터 요구사항 문서와 교차 검증 후 6개 항목 수정 (ContextDependency 타입 추가, ModelResponse item_id 통일 및 raw_output 추가, KnowledgeScore judge_order 명칭 통일, AgentScore 파싱 결과 필드 추가, AgentScore Optional 타입 명확화, HumanScoreDetail 구체화)*

---

## 문서 목적

이 문서는 BenchMate 시스템 전반에서 사용되는 모든 데이터 구조를 정의한다.
Claude Code로 개발 착수 시 이 문서의 구조를 그대로 코드로 옮긴다.

---

## 목차

1. LangGraph EvalState (중앙 상태 관리)
2. 평가 문항 구조 (Question)
3. Tool 정의 구조
4. 시나리오 구조 (Agent 평가용)
5. LLM 응답 수집 구조
6. 채점 결과 구조 (Knowledge / Agent)
7. 집계 결과 구조
8. 파일 저장 구조 및 경로

---

## 1. LangGraph EvalState

파이프라인 전체에서 공유되는 중앙 상태 객체.
모든 노드는 EvalState를 입력받아 EvalState를 반환한다.

```python
# /pipeline/state.py

from typing import TypedDict, List, Dict, Optional, Literal

# ── 하위 타입 정의 ──────────────────────────────────────────

class QuestionItem(TypedDict):
    id: str                          # "fin_001"
    domain: str                      # "finance"
    question: str                    # 평가 질문 텍스트
    reference_answer: str            # 담당자가 등록한 정답
    instance_rubric: str             # 핵심 채점 포인트 (Instance-Specific)
    difficulty: str                  # "easy" | "medium" | "hard"
    task_type: str                   # "explanation" | "calculation" | "summary" 등

class ToolDefinition(TypedDict):
    name: str                        # "search_loan_rate"
    description: str                 # Tool 설명
    parameters: List[Dict]           # 파라미터 목록 (name, type, required, description)
    mock_return: Dict                 # Simulated 반환값

class ContextDependency(TypedDict):
    from_turn: int                   # 값이 생성된 턴 인덱스
    to_turn: int                     # 해당 값을 사용해야 하는 턴 인덱스
    carried_value: str               # 전달되어야 할 파라미터 키 이름. 예: "annual_rate"
    description: str                 # 의존 관계 설명

class ScenarioItem(TypedDict):
    id: str                          # "fin_sc_001"
    domain: str
    scenario_type: str               # "single_A" | "single_B" | "single_C" | "multi"
    turns: List[Dict]                # 턴별 대화 정의
    expected_tool_calls: List[Dict]  # 정답 Tool 호출 목록 (turn별)
    context_dependency: List[ContextDependency]  # Multi-turn 맥락 의존 관계 (single_*은 빈 리스트)
    available_tools: List[str]       # 이 시나리오에서 사용 가능한 Tool 이름 목록

class ModelResponse(TypedDict):
    model_name: str
    item_id: str                     # question_id 또는 scenario_id. Knowledge/Agent 모드 통일
    response_text: str               # 모델 응답 (Knowledge)
    tool_call_output: Optional[Dict] # 모델의 Tool 호출 결과 — JSON 파싱 성공 시 (Agent)
    raw_output: Optional[str]        # Tool 호출 원본 문자열 — 파싱 전 보존. 디버깅 및 재시도용 (Agent)
    latency_ms: int
    input_tokens: int
    output_tokens: int
    status: str                      # "success" | "retry" | "failed"

class KnowledgeScore(TypedDict):
    question_id: str
    model_name: str
    accuracy: int                    # 1~5
    fluency: int                     # 1~5
    hallucination: int               # 1~5 (5=없음)
    domain_expertise: int            # 1~5
    utility: int                     # 1~5
    total: int                       # 합계 (max 25)
    reason: str                      # Judge 채점 이유
    judge_order: str                 # "ab" | "ba" (Position Bias 교차 평가용)

class AgentScore(TypedDict):
    scenario_id: str
    turn_index: int                  # Multi-turn: 몇 번째 턴
    model_name: str
    tool_name_extracted: Optional[str]  # evaluate_call이 파싱한 Tool 이름 (파싱 실패 시 None)
    params_extracted: Optional[Dict]    # evaluate_call이 파싱한 파라미터 dict (파싱 실패 시 None)
    call_correct: bool               # Tool 이름 일치 여부
    params_match: bool               # 파라미터 완전 일치 여부
    missing_params: List[str]        # 누락된 파라미터 키
    extra_params: List[str]          # 불필요하게 추가된 파라미터 키
    call_score: int                  # 0 or 1 (코드 기반 채점)
    slot_score: Optional[int]        # 0 or 1 (Judge). single_A/multi에서는 None
    relevance_score: Optional[int]   # 0 or 1 (Judge). single_A/B/multi에서는 None
    completion_score: Optional[int]  # 1~3 (Judge). 자연어 응답이 있는 턴에만 적용
    reason: str

class HumanScoreDetail(TypedDict):
    # Knowledge 수정 점수 (knowledge 또는 integrated 모드)
    accuracy: Optional[int]          # 1~5
    fluency: Optional[int]           # 1~5
    hallucination: Optional[int]     # 1~5
    domain_expertise: Optional[int]  # 1~5
    utility: Optional[int]           # 1~5
    # Agent 수정 점수 (agent 또는 integrated 모드)
    call_score: Optional[int]        # 0 or 1

class HumanReviewItem(TypedDict):
    item_id: str                     # question_id 또는 scenario_id
    item_type: str                   # "knowledge" | "agent"
    model_name: str
    judge_score: Dict                # Judge가 낸 점수 (KnowledgeScore 또는 AgentScore)
    human_score: Optional[HumanScoreDetail]  # 담당자 수정 점수. 검토 전: None
    review_reason: str               # 큐에 올라온 이유 (편차 큰 항목 / hallucination 낮음 / call 실패 / 랜덤)
    is_reviewed: bool

# ── 메인 EvalState ────────────────────────────────────────────

class EvalState(TypedDict):

    # 1. 평가 설정 (사용자 입력)
    eval_mode: str                   # "knowledge" | "agent" | "integrated"
    domain: str                      # "finance" | "legal" | "hr" | "cs" | "manufacturing"
    selected_models: List[str]       # ["solar-pro", "gpt-4o", "claude-sonnet"]

    # 2. 문항 및 시나리오
    questions: List[QuestionItem]           # Knowledge 문항
    scenarios: List[ScenarioItem]           # Agent 시나리오
    available_tools: List[ToolDefinition]   # 이번 평가에서 사용할 Tool 목록
    rubric_text: str                        # 도메인 기본 루브릭 텍스트

    # 3. 응답 수집
    model_responses: List[ModelResponse]   # 전체 모델 응답

    # 4. 채점 결과
    knowledge_scores_ab: List[KnowledgeScore]   # A→B 순서 채점
    knowledge_scores_ba: List[KnowledgeScore]   # B→A 순서 채점 (Position Bias 제거)
    knowledge_scores_final: List[KnowledgeScore] # 평균 최종 점수
    agent_scores: List[AgentScore]               # Agent 채점 결과
    retry_count: int                             # 채점 재시도 카운터 (최대 3)

    # 5. Human Review
    human_review_queue: List[HumanReviewItem]
    judge_reliability: Optional[float]           # Judge-Human 일치율 (%)

    # 6. 집계 및 출력
    summary_table: Optional[Dict]               # 모델 × 도메인 × 기준 집계 테이블
    estimated_cost: Optional[Dict]              # 모델별 추정 API 비용
    pm_report_text: Optional[str]               # PM 해석 리포트 (마크다운)
    eval_session_id: str                        # 세션 고유 ID (타임스탬프 기반)
```

---

## 2. 평가 문항 구조 (Question JSON)

### 스키마

```json
{
  "domain": "finance",
  "domain_name_ko": "금융",
  "questions": [
    {
      "id": "fin_001",
      "domain": "finance",
      "question": "신용대출 금리 산정 시 고려하는 주요 요소 3가지를 설명하시오.",
      "reference_answer": "신용등급, 기준금리(COFIX), 가산금리를 고려한다. 신용등급이 높을수록 가산금리가 낮아지며, 기준금리에 가산금리를 더한 값이 최종 대출 금리가 된다.",
      "instance_rubric": "COFIX, 신용등급, 가산금리 세 가지를 모두 언급했는가? 각 요소가 금리에 미치는 방향(정비례/반비례)을 명시했는가? 실제 금리 계산 구조(기준금리+가산금리)를 설명했는가?",
      "difficulty": "medium",
      "task_type": "explanation",
      "evaluation_focus": ["accuracy", "domain_expertise"]
    }
  ]
}
```

### 필드 정의

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| id | string | ✅ | 도메인 접두사 + 번호. 예: fin_001, leg_003 |
| domain | string | ✅ | finance / legal / hr / cs / manufacturing |
| question | string | ✅ | 평가 질문 텍스트 (10자 이상) |
| reference_answer | string | ✅ | 담당자가 등록한 정답. Judge의 채점 기준점 |
| instance_rubric | string | ✅ | 이 문항에서 특히 봐야 할 채점 포인트. Judge 프롬프트에 주입됨 |
| difficulty | enum | ✅ | easy / medium / hard |
| task_type | string | ✅ | explanation / calculation / summary / translation / comparison |
| evaluation_focus | list | 선택 | 이 문항에서 가중치를 줄 루브릭 항목 |

### 파일 경로

```
/data/questions/
  ├── finance.json
  ├── legal.json
  ├── hr.json
  ├── cs.json
  └── manufacturing.json
```

---

## 3. Tool 정의 구조

### 스키마

```json
{
  "domain": "finance",
  "tools": [
    {
      "name": "search_loan_rate",
      "description": "고객 ID와 신용등급을 입력받아 적용 가능한 대출 금리를 조회합니다.",
      "parameters": [
        {
          "name": "customer_id",
          "type": "string",
          "required": true,
          "description": "고객 고유 식별자. 예: C-1234"
        },
        {
          "name": "credit_score",
          "type": "integer",
          "required": true,
          "description": "신용등급 점수. 300~850 범위"
        }
      ],
      "mock_return": {
        "customer_id": "C-1234",
        "base_rate": 3.5,
        "spread_rate": 1.2,
        "final_rate": 4.7,
        "product_name": "일반 신용대출"
      }
    },
    {
      "name": "calculate_interest",
      "description": "원금, 연이율, 기간을 입력받아 이자를 계산합니다.",
      "parameters": [
        {
          "name": "principal",
          "type": "integer",
          "required": true,
          "description": "대출 원금 (원)"
        },
        {
          "name": "annual_rate",
          "type": "float",
          "required": true,
          "description": "연이율 (%). 예: 4.7"
        },
        {
          "name": "term_months",
          "type": "integer",
          "required": true,
          "description": "대출 기간 (개월)"
        }
      ],
      "mock_return": {
        "principal": 30000000,
        "annual_rate": 4.7,
        "term_months": 36,
        "total_interest": 2162040,
        "monthly_payment": 895056
      }
    }
  ]
}
```

### 파일 경로

```
/data/tools/
  ├── finance_tools.json
  ├── legal_tools.json
  ├── hr_tools.json
  ├── cs_tools.json
  └── manufacturing_tools.json
```

---

## 4. 시나리오 구조 (Agent 평가용)

### Single-turn 시나리오 스키마

```json
{
  "domain": "finance",
  "scenarios": [
    {
      "id": "fin_sc_001",
      "domain": "finance",
      "scenario_type": "single_A",
      "description": "정상 호출 — 고객 대출 금리 조회",
      "turns": [
        {
          "turn_index": 0,
          "role": "user",
          "content": "홍길동 고객(ID: C-1234, 신용점수: 720)의 대출 금리 조회해줘."
        }
      ],
      "expected_tool_calls": [
        {
          "turn_index": 0,
          "tool_name": "search_loan_rate",
          "parameters": {
            "customer_id": "C-1234",
            "credit_score": 720
          }
        }
      ],
      "available_tools": ["search_loan_rate", "calculate_interest"],
      "evaluation_focus": ["call"]
    },
    {
      "id": "fin_sc_002",
      "domain": "finance",
      "scenario_type": "single_B",
      "description": "정보 부족 — 고객 ID 없이 금리 조회 요청",
      "turns": [
        {
          "turn_index": 0,
          "role": "user",
          "content": "고객 대출 금리 조회해줘."
        }
      ],
      "expected_tool_calls": [],
      "expected_slot_response": "고객 ID와 신용점수를 알려주시겠어요?",
      "available_tools": ["search_loan_rate"],
      "evaluation_focus": ["slot"]
    },
    {
      "id": "fin_sc_003",
      "domain": "finance",
      "scenario_type": "single_C",
      "description": "불가능한 요청 — 경쟁사 금리 데이터 조회",
      "turns": [
        {
          "turn_index": 0,
          "role": "user",
          "content": "KB국민은행 내부 금리 데이터 조회해줘."
        }
      ],
      "expected_tool_calls": [],
      "expected_rejection": true,
      "available_tools": ["search_loan_rate"],
      "evaluation_focus": ["relevance"]
    }
  ]
}
```

### Multi-turn 시나리오 스키마

```json
{
  "id": "fin_sc_multi_001",
  "domain": "finance",
  "scenario_type": "multi",
  "description": "고객 대출 금리 조회 후 월 상환액 계산",
  "turns": [
    {
      "turn_index": 0,
      "role": "user",
      "content": "홍길동 고객(ID: C-1234, 신용점수: 720)의 대출 금리 조회해줘."
    },
    {
      "turn_index": 1,
      "role": "tool_result",
      "content": "{\"customer_id\": \"C-1234\", \"final_rate\": 4.7, \"product_name\": \"일반 신용대출\"}"
    },
    {
      "turn_index": 2,
      "role": "user",
      "content": "그럼 3천만원 빌리면 36개월 기준 월 상환액은 얼마야?"
    },
    {
      "turn_index": 3,
      "role": "tool_result",
      "content": "{\"principal\": 30000000, \"annual_rate\": 4.7, \"term_months\": 36, \"monthly_payment\": 895056}"
    },
    {
      "turn_index": 4,
      "role": "user",
      "content": "알겠어, 최종 정리해줘."
    }
  ],
  "expected_tool_calls": [
    {
      "turn_index": 0,
      "tool_name": "search_loan_rate",
      "parameters": {"customer_id": "C-1234", "credit_score": 720}
    },
    {
      "turn_index": 2,
      "tool_name": "calculate_interest",
      "parameters": {"principal": 30000000, "annual_rate": 4.7, "term_months": 36}
    }
  ],
  "context_dependency": [
    {
      "from_turn": 1,
      "to_turn": 2,
      "carried_value": "annual_rate",
      "description": "Turn 1의 final_rate 4.7을 Turn 2의 annual_rate로 사용해야 함"
    }
  ],
  "available_tools": ["search_loan_rate", "calculate_interest"],
  "evaluation_focus": ["call", "completion", "context_retention"]
}
```

### 파일 경로

```
/data/scenarios/
  ├── finance_scenarios.json
  ├── legal_scenarios.json
  ├── hr_scenarios.json
  ├── cs_scenarios.json
  └── manufacturing_scenarios.json
```

---

## 5. 루브릭 프롬프트 구조

### Knowledge Judge 프롬프트 템플릿

```
/prompts/knowledge_judge_template.txt

당신은 한국어 기업 도메인 LLM 응답을 평가하는 전문 심사관입니다.

[평가 도메인]
{{ domain_name }}

[평가 문항]
{{ question }}

[Reference Answer (정답)]
{{ reference_answer }}

[이 문항의 핵심 채점 포인트]
{{ instance_rubric }}

[평가 대상 응답]
{{ model_response }}

[평가 기준]
- 정확성 (accuracy, 1-5점): 사실 오류 없이 정확한 정보를 제공하는가.
  핵심 채점 포인트를 정확성 점수에 가장 강하게 반영하세요.
- 한국어 자연성 (fluency, 1-5점): 자연스러운 한국어 표현과 문법인가.
- 할루시네이션 (hallucination, 1-5점): 없는 정보를 만들어내지 않는가. (5점=전혀 없음)
- 도메인 전문성 (domain_expertise, 1-5점): 해당 도메인 용어를 정확히 사용하는가.
- 응답 적절성 (utility, 1-5점): 질문 의도에 맞는 답변 형식과 길이인가.

[출력 형식 - 반드시 JSON만 출력하세요]
{
  "accuracy": <1-5>,
  "fluency": <1-5>,
  "hallucination": <1-5>,
  "domain_expertise": <1-5>,
  "utility": <1-5>,
  "total": <5-25>,
  "reason": "<채점 이유를 2-3문장으로>"
}
```

### Agent Judge 프롬프트 템플릿 (slot / relevance / completion용)

```
/prompts/agent_judge_template.txt

당신은 AI Agent의 Tool 사용 능력을 평가하는 전문 심사관입니다.

[평가 항목: {{ eval_type }}]
{% if eval_type == "slot" %}
사용자 요청에 필요한 정보가 누락됐을 때, 적절한 질문으로 정보를 요청했는가?
{% elif eval_type == "relevance" %}
수행 불가능한 요청에 대해 적절히 거절하고 이유를 설명했는가?
{% elif eval_type == "completion" %}
Tool 실행 결과를 사용자에게 자연스럽고 정확하게 요약·전달했는가?
{% endif %}

[사용자 입력]
{{ user_input }}

[모델 응답]
{{ model_response }}

{% if eval_type == "completion" %}
[Tool 실행 결과]
{{ tool_result }}
{% endif %}

[출력 형식 - 반드시 JSON만 출력하세요]
{
  "score": <0 또는 1 (slot/relevance) | 1-3 (completion)>,
  "reason": "<판단 이유를 1-2문장으로>"
}
```

### 파일 경로

```
/prompts/
  ├── knowledge_judge_template.txt
  └── agent_judge_template.txt
```

---

## 6. 채점 결과 구조

### Knowledge 채점 JSON 출력 (파싱 후)

```json
{
  "question_id": "fin_001",
  "model_name": "solar-pro",
  "judge_order": "ab",
  "accuracy": 4,
  "fluency": 5,
  "hallucination": 5,
  "domain_expertise": 3,
  "utility": 4,
  "total": 21,
  "reason": "COFIX와 가산금리는 언급했으나 신용등급과 금리의 반비례 관계를 명시하지 않았습니다."
}
```

### Agent 채점 JSON 출력

```json
{
  "scenario_id": "fin_sc_001",
  "turn_index": 0,
  "model_name": "solar-pro",
  "tool_name_extracted": "search_loan_rate",
  "params_extracted": {"customer_id": "C-1234", "credit_score": 720},
  "call_correct": true,
  "params_match": true,
  "missing_params": [],
  "extra_params": [],
  "call_score": 1,
  "slot_score": null,
  "relevance_score": null,
  "completion_score": null,
  "reason": "search_loan_rate 호출, customer_id='C-1234', credit_score=720 모두 정확"
}
```

---

## 7. 집계 결과 구조

### Summary Table (모델 × 도메인 × 기준)

```python
# DataFrame 구조
# index: model_name
# columns: MultiIndex (domain, criterion)

{
  "solar-pro": {
    "finance": {
      "accuracy": 3.8,
      "fluency": 4.5,
      "hallucination": 4.2,
      "domain_expertise": 3.5,
      "utility": 4.0,
      "knowledge_total": 20.0,
      "call_score": 0.72,
      "slot_score": 0.80,
      "relevance_score": 0.90,
      "completion_score": 2.1,
      "agent_total": 4.52
    }
  },
  "gpt-4o": { ... }
}
```

### Eval Session JSON (내보내기용)

```json
{
  "session_id": "eval_20260315_143022",
  "eval_mode": "integrated",
  "domain": "finance",
  "selected_models": ["solar-pro", "gpt-4o", "claude-sonnet"],
  "question_count": 10,
  "scenario_count": 8,
  "judge_model": "Qwen/Qwen2.5-7B-Instruct",
  "judge_reliability": 0.84,
  "summary_table": { ... },
  "pm_report_text": "## BenchMate 평가 리포트\n...",
  "created_at": "2026-03-15T14:30:22+09:00"
}
```

---

## 8. 파일 저장 구조 전체

```
benchmate/
├── CLAUDE.md                          # Claude Code 프로젝트 설명
├── app.py                             # Streamlit 진입점
├── requirements.txt
├── .env                               # API 키 (git 제외)
│
├── pipeline/                          # LangGraph 파이프라인
│   ├── state.py                       # EvalState TypedDict 정의
│   ├── graph.py                       # 전체 그래프 조립
│   └── nodes/                         # 각 노드 함수
│       ├── load_scenarios.py
│       ├── route_mode.py
│       ├── generate_responses.py
│       ├── judge_knowledge.py
│       ├── evaluate_call.py
│       ├── judge_agent.py
│       ├── validate_scores.py
│       ├── flag_human_review.py
│       ├── aggregate_results.py
│       └── generate_report.py
│
├── data/
│   ├── questions/                     # 도메인별 문항 JSON
│   │   ├── finance.json
│   │   ├── legal.json
│   │   ├── hr.json
│   │   ├── cs.json
│   │   └── manufacturing.json
│   ├── tools/                         # 도메인별 Tool 정의 JSON
│   │   ├── finance_tools.json
│   │   └── ...
│   └── scenarios/                     # 도메인별 Agent 시나리오 JSON
│       ├── finance_scenarios.json
│       └── ...
│
├── prompts/                           # Judge 프롬프트 템플릿
│   ├── knowledge_judge_template.txt
│   └── agent_judge_template.txt
│
├── ui/                                # Streamlit 화면
│   ├── screen1_mode_select.py
│   ├── screen2_domain_tool.py
│   ├── screen3_scenario.py
│   ├── screen4_run.py
│   ├── screen5_dashboard.py
│   ├── screen6_human_review.py
│   └── screen7_report.py
│
├── evaluators/                        # 채점 로직
│   ├── tool_call_evaluator.py         # call 항목 코드 기반 채점
│   └── score_aggregator.py            # 집계 로직
│
├── output/                            # 평가 세션 결과 저장
│   └── eval_20260315_143022.json
│
└── tests/
    ├── test_state.py
    ├── test_tool_call_evaluator.py
    └── test_pipeline.py
```

---

## 9. 핵심 설계 원칙

**원칙 1. EvalState는 단일 진실 공급원(Single Source of Truth)**
모든 노드는 EvalState만 참조한다. 노드 간 직접 데이터 전달 없음.

**원칙 2. call 채점은 코드, 나머지는 Judge**
Tool 이름·파라미터 정확도는 JSON 파싱 후 코드로 비교한다. LLM Judge 개입 없음.
slot / relevance / completion만 Judge를 사용한다.

**원칙 3. Position Bias 제거는 Knowledge에만 적용**
A→B, B→A 교차 평가는 Knowledge 채점에만 적용한다.
Agent call 채점은 코드 기반이라 불필요하다.

**원칙 4. Mock 반환값은 scenario JSON에 포함**
Tool 실행 결과(mock_return)는 Tool 정의 JSON에, 턴별 반환값은 scenario JSON의 turns에 미리 정의한다. 파이프라인 실행 시 별도 API 호출 없이 사전 정의된 값을 사용한다.

**원칙 5. Judge 출력은 항상 JSON 파싱 후 저장**
Judge 원본 응답(raw string)과 파싱 결과(dict)를 모두 EvalState에 보존한다.
파싱 실패 시 retry_judge 노드로 분기 (최대 3회).