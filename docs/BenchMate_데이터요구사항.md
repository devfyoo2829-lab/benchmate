# 데이터 요구사항 정의서

# BenchMate — 데이터 요구사항 문서

## Data Requirements Document

*작성일: 2026.03 | 작성자: 곽승연 | 상위 문서: BenchMate 기획서 최종연관 문서: 데이터 구조 설계 문서*

---

## 문서 목적

BenchMate 시스템 구현에 필요한 모든 데이터를 식별하고,
각 데이터의 종류·소스·수집 방법·저장 위치·유효성 조건을 정의한다.

---

## 목차

1. 데이터 분류 체계
2. A. 사용자 입력 데이터
3. B. 시스템 구성 데이터
4. C. API 수집 데이터
5. D. 파이프라인 생성 데이터
6. 데이터 흐름 요약
7. 유효성 검증 및 예외 처리 기준
8. 데이터 품질 보장 원칙

---

## 1. 데이터 분류 체계

전체 데이터를 생성 주체와 시점에 따라 4가지 유형으로 분류한다.

| 유형 | 정의 | 예시 |
| --- | --- | --- |
| **A. 사용자 입력** | 담당자가 Streamlit UI에서 직접 입력 | 평가 질문, 정답, 핵심 채점 포인트 |
| **B. 시스템 구성** | 서비스 운영을 위해 개발자가 사전 구축 | 도메인 문항 세트, Tool 정의, 루브릭 프롬프트 |
| **C. API 수집** | 외부 LLM API 호출을 통해 자동 수집 | 피평가 모델 응답, Judge 채점 원본 |
| **D. 파이프라인 생성** | LangGraph 노드 처리 과정에서 자동 생성 | 파싱된 점수, 집계 테이블, PM 리포트 |

---

## 2. A. 사용자 입력 데이터

담당자가 Streamlit UI(Screen 1~3, 6)에서 직접 입력하는 데이터.
EvalState 초기값을 구성하며, 파이프라인 실행 전에 모두 확정된다.

### A-1. 평가 설정

| 데이터명 | 설명 | 타입 | 입력 위치 | 유효성 조건 |
| --- | --- | --- | --- | --- |
| eval_mode | 평가 모드 | enum | Screen 1 라디오 버튼 | knowledge / agent / integrated 중 하나 |
| domain | 평가 도메인 | enum | Screen 2 카드 선택 | finance / legal / hr / cs / manufacturing 중 하나 |
| selected_models | 비교할 모델 목록 | list[string] | Screen 4 멀티셀렉트 | 2개 이상 선택 필수 |

### A-2. Knowledge 문항 입력

eval_mode가 knowledge 또는 integrated일 때 활성화.

| 데이터명 | 설명 | 타입 | 입력 위치 | 유효성 조건 |
| --- | --- | --- | --- | --- |
| question | 평가 질문 텍스트 | string | Screen 3 텍스트 입력 | 10자 이상, 1000자 이하 |
| reference_answer | 담당자가 알고 있는 정답 | string | Screen 3 텍스트 입력 | 10자 이상. 필수. Judge 채점 기준점 |
| instance_rubric | 이 문항의 핵심 채점 포인트 | string | Screen 3 텍스트 입력 | 10자 이상. 필수. Judge 프롬프트에 직접 주입됨 |
| difficulty | 문항 난이도 | enum | Screen 3 셀렉트박스 | easy / medium / hard |
| task_type | 태스크 유형 | string | Screen 3 셀렉트박스 | explanation / calculation / summary / translation / comparison |

> **instance_rubric 입력 가이드 (UI에 안내 텍스트로 표시)**
"이 문항에서 LLM이 반드시 언급해야 할 핵심 포인트를 구체적으로 써주세요."
예시: "COFIX, 신용등급, 가산금리 세 가지를 모두 언급했는가? 금리와의 관계(정비례/반비례)를 설명했는가?"
> 

### A-3. Agent 시나리오 입력

eval_mode가 agent 또는 integrated일 때 활성화.

**Single-turn 시나리오**

| 데이터명 | 설명 | 타입 | 입력 위치 | 유효성 조건 |
| --- | --- | --- | --- | --- |
| scenario_type | 시나리오 유형 | enum | Screen 3 선택 | single_A / single_B / single_C |
| user_input | 사용자 요청 텍스트 | string | Screen 3 텍스트 입력 | 5자 이상 |
| expected_tool_name | 정답 Tool 이름 (Type A만) | string | Screen 3 드롭다운 | 사전 정의 Tool 목록 중 선택 |
| expected_parameters | 정답 파라미터 (Type A만) | dict | Screen 3 동적 입력 | 각 키·값 타입 일치 필요 |
| available_tools | 이 시나리오에서 제공할 Tool | list
[string] | Screen 3 멀티셀렉트 | 1개 이상 선택 |

**Multi-turn 시나리오**

| 데이터명 | 설명 | 타입 | 입력 위치 | 유효성 조건 |
| --- | --- | --- | --- | --- |
| turns | 턴별 대화 정의 | list[dict] | Screen 3 턴 빌더 UI | 3턴 이상, 5턴 이하 |
| expected_tool_calls | 턴별 정답 Tool 호출 | list[dict] | Screen 3 턴 빌더 UI | turn_index, tool_name, parameters 포함 필수 |
| context_dependency | 이전 턴 값을 다음 턴에서 써야 하는 의존 관계 | list[dict] | Screen 3 선택 입력 | from_turn, to_turn, carried_value 포함 |

### A-4. Human Review 수정 점수 (Screen 6)

| 데이터명 | 설명 | 타입 | 입력 위치 | 유효성 조건 |
| --- | --- | --- | --- | --- |
| human_accuracy | 수정된 정확성 점수 | int | Screen 6 슬라이더 | 1~5 정수 |
| human_fluency | 수정된 자연성 점수 | int | Screen 6 슬라이더 | 1~5 정수 |
| human_hallucination | 수정된 할루시네이션 점수 | int | Screen 6 슬라이더 | 1~5 정수 |
| human_domain_expertise | 수정된 전문성 점수 | int | Screen 6 슬라이더 | 1~5 정수 |
| human_utility | 수정된 적절성 점수 | int | Screen 6 슬라이더 | 1~5 정수 |
| human_call_score | Agent call 항목 수정 점수 | int | Screen 6 라디오 | 0 또는 1 |

---

## 3. B. 시스템 구성 데이터

개발자(곽승연)가 사전에 구축하고 파일로 저장하는 데이터.
파이프라인 실행 시 자동으로 로드된다.

### B-1. 도메인 문항 세트

| 항목 | 내용 |
| --- | --- |
| 설명 | 도메인별 사전 구축 평가 문항. 담당자가 선택해서 쓰거나 자신의 문항 기준점으로 활용 |
| 파일 경로 | /data/questions/{domain}.json |
| 파일 형식 | JSON (QuestionItem 배열) |
| 생성 방법 | Step 1: 개발자가 시드 문항 5~10개 직접 작성 (BiGGen Bench 방법론) → Step 2: GPT-4o로 추가 문항 증강 생성 (시드 문항을 in-context 예시로 제공) → Step 3: 의미적 유사도 낮은 후보 선택 → Step 4: 개발자 최종 검토·수정 |
| 관리 주체 | 개발자 (수동 유지보수) |
| 최소 문항 수 | 도메인당 15개 이상 (금융 20개, 나머지 15개씩) |

**도메인별 문항 수 및 태스크 유형 분포**

| 도메인 | 총 문항 | explanation | calculation | summary | 기타 |
| --- | --- | --- | --- | --- | --- |
| 금융 | 20개 | 8 | 6 | 3 | 3 |
| 법률·규정 | 15개 | 7 | 0 | 5 | 3 |
| 인사·HR | 15개 | 6 | 0 | 4 | 5 |
| 고객응대·CS | 15개 | 4 | 0 | 3 | 8 |
| 제조·기술문서 | 15개 | 5 | 2 | 5 | 3 |

### B-2. Tool 정의 세트

| 항목 | 내용 |
| --- | --- |
| 설명 | 도메인별 사전 정의 Tool. name, description, parameters, mock_return 포함 |
| 파일 경로 | /data/tools/{domain}_tools.json |
| 파일 형식 | JSON (ToolDefinition 배열) |
| 생성 방법 | 개발자가 도메인별 실제 업무 흐름을 분석해 수동 작성 |
| Tool 수 | 도메인당 5개 이상 |

**도메인별 필수 Tool 목록**

| 도메인 | Tool 이름 | 설명 |
| --- | --- | --- |
| 금융 | search_loan_rate | 고객 대출 금리 조회 |
| 금융 | calculate_interest | 이자 계산 |
| 금융 | get_product_info | 금융 상품 정보 조회 |
| 금융 | search_customer | 고객 기본 정보 조회 |
| 금융 | calculate_monthly_payment | 월 상환액 계산 |
| 법률·규정 | search_regulation | 법령·규정 검색 |
| 법률·규정 | check_compliance | 규정 준수 여부 확인 |
| 법률·규정 | get_contract_template | 계약서 템플릿 조회 |
| 인사·HR | search_hr_policy | 인사 정책 검색 |
| 인사·HR | get_employee_info | 직원 정보 조회 |
| 인사·HR | create_feedback_draft | 성과 피드백 초안 생성 |
| 고객응대·CS | search_faq | FAQ 검색 |
| 고객응대·CS | get_customer_history | 고객 응대 이력 조회 |
| 고객응대·CS | create_response_draft | 응답 초안 생성 |
| 제조·기술 | search_manual | 장비 매뉴얼 검색 |
| 제조·기술 | get_defect_history | 불량 이력 조회 |
| 제조·기술 | translate_technical_term | 기술 용어 번역 |

### B-3. Agent 시나리오 세트

| 항목 | 내용 |
| --- | --- |
| 설명 | 도메인별 사전 구축 Agent 평가 시나리오 (Single-turn A/B/C + Multi-turn) |
| 파일 경로 | /data/scenarios/{domain}_scenarios.json |
| 파일 형식 | JSON (ScenarioItem 배열) |
| 생성 방법 | 개발자가 수동 작성 |
| 최소 시나리오 수 | 도메인당 7개 이상 (A형 2개, B형 2개, C형 2개, Multi-turn 1개) |

### B-4. Judge 프롬프트 템플릿

| 항목 | 내용 |
| --- | --- |
| 설명 | Knowledge Judge용, Agent Judge(slot/relevance/completion)용 프롬프트 템플릿 |
| 파일 경로 | /prompts/knowledge_judge_template.txt, /prompts/agent_judge_template.txt |
| 파일 형식 | Jinja2 템플릿 (변수: {{ domain_name }}, {{ instance_rubric }}, {{ question }} 등) |
| 생성 방법 | 개발자 직접 설계. 금융 시드 문항 5개로 파일럿 채점 후 반복 수정 |
| 검증 목표 | Judge-Human 일치율 70% 이상 |

### B-5. 모델 API 설정

| 항목 | 내용 |
| --- | --- |
| 설명 | 피평가 모델 및 Judge 모델의 API 키, 엔드포인트, 호출 파라미터 |
| 파일 경로 | .env (API 키, git 제외), /config/model_config.yaml |
| 관리 방법 | .gitignore에 .env 추가 필수. API 키를 코드에 직접 삽입 절대 금지 |

**모델별 API 설정 항목**

| 모델 | 제공사 | 환경변수 키 | 주요 파라미터 |
| --- | --- | --- | --- |
| Solar Pro | Upstage | UPSTAGE_API_KEY | temperature=0.1, max_tokens=2048 |
| GPT-4o | OpenAI | OPENAI_API_KEY | temperature=0.1, max_tokens=2048 |
| Claude Sonnet | Anthropic | ANTHROPIC_API_KEY | temperature=0.1, max_tokens=2048 |
| HyperCLOVA X | NAVER Cloud | HCX_API_KEY | 접근 가능 시 추가 |
| EXAONE 4.0 | LG AI Research | EXAONE_API_KEY | 접근 가능 시 추가 |
| Qwen 2.5-32B (Judge) | HuggingFace | HF_TOKEN | temperature=0.0, max_tokens=512 |

### B-6. 모델 비용 테이블

| 항목 | 내용 |
| --- | --- |
| 설명 | 모델별 API 단가 (1K 토큰 기준, 입력/출력 구분) |
| 파일 경로 | /data/pricing.json |
| 생성 방법 | 각 사 공식 문서 참조. 분기별 업데이트 |
| 활용 | PM 리포트의 비용 대비 성능 분석 섹션에서 사용 |

---

## 4. C. API 수집 데이터

LangGraph 파이프라인 실행 중 외부 LLM API 호출로 자동 수집되는 데이터.

### C-1. 피평가 모델 응답 (Knowledge)

| 데이터명 | 설명 | 타입 | 수집 노드 | 저장 위치 |
| --- | --- | --- | --- | --- |
| response_text | 모델의 자연어 응답 텍스트 | string | generate_responses | EvalState.model_responses |
| latency_ms | API 응답 시간 (밀리초) | int | generate_responses | EvalState.model_responses |
| input_tokens | 입력 토큰 수 | int | generate_responses | EvalState.model_responses |
| output_tokens | 출력 토큰 수 | int | generate_responses | EvalState.model_responses |
| status | 호출 성공/실패 상태 | enum | generate_responses | EvalState.model_responses |

**status 값 정의**

| 값 | 의미 |
| --- | --- |
| success | API 호출 성공, 응답 수신 완료 |
| retry | 응답 실패, 재시도 중 (retry_count 증가) |
| failed | 최대 재시도(3회) 초과, 해당 모델 결과 제외 |

### C-2. 피평가 모델 Tool 호출 출력 (Agent)

| 데이터명 | 설명 | 타입 | 수집 노드 | 저장 위치 |
| --- | --- | --- | --- | --- |
| tool_call_output | 모델이 생성한 Tool 호출 JSON 전체 | dict or
string | generate_tool_calls | EvalState.model_responses |
| tool_name_extracted | 파싱된 Tool 이름 | string | evaluate_call | EvalState.agent_scores |
| params_extracted | 파싱된 파라미터 | dict | evaluate_call | EvalState.agent_scores |
| raw_output | 파싱 전 원본 문자열 (디버깅용) | string | generate_tool_calls | EvalState.model_responses |

**Tool 호출 출력 기대 형식**

```json
{
  "tool_name": "search_loan_rate",
  "parameters": {
    "customer_id": "C-1234",
    "credit_score": 720
  }
}
```

모델이 위 형식을 따르지 않을 경우 evaluate_call 노드에서 파싱 시도 후 실패 처리.

### C-3. Judge 모델 채점 원본 (Knowledge)

| 데이터명 | 설명 | 타입 | 수집 노드 | 저장 위치 |
| --- | --- | --- | --- | --- |
| judge_raw_output | Qwen 2.5 Judge 원본 응답 텍스트 | string | judge_knowledge | EvalState (임시 보존) |
| judge_parsed_score | JSON 파싱 완료된 채점 결과 | dict | validate_scores | EvalState.knowledge_scores_ab / _ba |
| judge_order | 채점 순서 (Position Bias 교차 평가용) | enum | judge_knowledge | EvalState.knowledge_scores_ab / _ba |

**Judge 원본 응답 기대 형식**

```json
{
  "accuracy": 4,
  "fluency": 5,
  "hallucination": 5,
  "domain_expertise": 3,
  "utility": 4,
  "total": 21,
  "reason": "COFIX와 가산금리는 언급했으나 신용등급과의 관계를 명시하지 않았습니다."
}
```

### C-4. Judge 모델 채점 원본 (Agent)

| 데이터명 | 설명 | 타입 | 수집 노드 | 저장 위치 |
| --- | --- | --- | --- | --- |
| slot_judge_raw | slot 항목 Judge 원본 | string | judge_agent | EvalState (임시) |
| relevance_judge_raw | relevance 항목 Judge 원본 | string | judge_agent | EvalState (임시) |
| completion_judge_raw | completion 항목 Judge 원본 | string | judge_agent | EvalState (임시) |

**Agent Judge 원본 기대 형식**

```json
{
  "score": 1,
  "reason": "고객 ID가 누락된 상황에서 적절히 정보를 요청했습니다."
}
```

---

## 5. D. 파이프라인 생성 데이터

LangGraph 노드 처리 과정에서 자동으로 생성되고 EvalState에 누적되는 데이터.

### D-1. Knowledge 채점 결과 (파싱 완료)

| 데이터명 | 생성 노드 | 타입 | 저장 위치 | 설명 |
| --- | --- | --- | --- | --- |
| knowledge_scores_ab | validate_scores | list[KnowledgeScore] | EvalState | A→B 순서 채점 결과 |
| knowledge_scores_ba | validate_scores | list[KnowledgeScore] | EvalState | B→A 순서 채점 결과 |
| knowledge_scores_final | aggregate_results | list[KnowledgeScore] | EvalState | ab와 ba 평균. 최종 Knowledge 점수 |

**Position Bias 제거 평균 계산 방식**

```python
final_score[criterion] = (ab_score[criterion] + ba_score[criterion]) / 2
# criterion: accuracy, fluency, hallucination, domain_expertise, utility
```

### D-2. Agent 채점 결과

| 데이터명 | 생성 노드 | 채점 방식 | 저장 위치 |
| --- | --- | --- | --- |
| call_score | evaluate_call | 코드 기반 JSON 비교 (Judge 없음) | EvalState.agent_scores |
| slot_score | judge_agent | Qwen 2.5 Judge | EvalState.agent_scores |
| relevance_score | judge_agent | Qwen 2.5 Judge | EvalState.agent_scores |
| completion_score | judge_agent | Qwen 2.5 Judge | EvalState.agent_scores |

**call 항목 코드 기반 채점 로직 (핵심)**

```
입력: expected_tool_call (정답), model_tool_call (모델 출력)
처리:
  1. model_tool_call JSON 파싱 시도
  2. Tool 이름 일치 여부 확인 (snake_case 정규화 후 비교)
  3. 파라미터 키 일치 여부 확인
  4. 파라미터 값 일치 여부 확인 (타입 캐스팅 허용: "720" == 720)
  5. 누락 파라미터, 불필요 파라미터 목록 생성
출력: {call_correct, params_match, missing_params, extra_params, call_score}
```

### D-3. Human Review 큐

**Human Review 큐 선별 기준 (OR 조건)**

| 조건 | 기준값 | 이유 |
| --- | --- | --- |
| Knowledge 교차 평가 편차 | |ab_total - ba_total| ≥ 3점 | Position Bias 영향이 큰 항목 |
| hallucination 점수 낮음 | hallucination ≤ 2 | 고위험 항목 우선 검토 |
| call 항목 완전 실패 | call_score == 0 | Tool 호출 실패 항목 |
| 랜덤 샘플 | 전체 문항·시나리오의 20% | Judge 전반 신뢰도 확인 |

### D-4. 집계 결과

| 데이터명 | 생성 노드 | 타입 | 설명 |
| --- | --- | --- | --- |
| summary_table | aggregate_results | dict (중첩) | 모델 × 도메인 × 기준 집계. 시각화와 리포트의 입력값 |
| judge_reliability | aggregate_results | float | Human Review 일치율. |(일치 항목 수 / 전체 검토 항목 수)| × 100 |
| estimated_cost | aggregate_results | dict | 모델별 총 토큰 수 × 단가 계산 결과 |

**judge_reliability 계산 방식**

```
Judge 점수와 Human 수정 점수의 total 차이가 ±2점 이내 → "일치"로 판정
judge_reliability = (일치 항목 수 / 전체 검토 완료 항목 수) × 100
```

### D-5. PM 해석 리포트

| 데이터명 | 생성 노드 | 타입 | 설명 |
| --- | --- | --- | --- |
| pm_report_text | generate_report | string (마크다운) | 자동 생성된 PM 관점 분석 리포트 |

**PM 리포트 구성 섹션**

```
1. 평가 요약 (모드, 도메인, 문항/시나리오 수, Judge 신뢰도)
2. 종합 추천 모델 및 근거
3. Knowledge vs Agent 괴리 분석
   예: "A 모델은 지식 점수가 높지만 Tool 파라미터 정확도가 낮아
       텍스트 생성 업무에 적합하고 Tool 기반 조회 업무에는 부적합합니다."
4. 도메인별 강점 모델
5. 고위험 항목 경고 (hallucination 높음, call 실패율 높음)
6. 비용 대비 성능 분석
7. 도입 우선순위 제안 3가지
```

### D-6. 세션 스냅샷

| 데이터명 | 생성 시점 | 파일 경로 | 타입 |
| --- | --- | --- | --- |
| eval_session_json | 파이프라인 완료 후 자동 저장 | /output/eval_{session_id}.json | JSON |

**세션 스냅샷 포함 데이터**

```
session_id, eval_mode, domain, selected_models
문항/시나리오 수, Judge 모델명
judge_reliability
summary_table
pm_report_text
created_at (KST)
```

---

## 6. 데이터 흐름 요약

```
[A. 사용자 입력] ─────────────────────────────────────────
  eval_mode, domain, selected_models
  questions: question + reference_answer + instance_rubric
  scenarios: turns + expected_tool_calls + context_dependency
                    ↓
         EvalState 초기값 설정
                    ↓
[B. 시스템 구성] 주입 ─────────────────────────────────────
  rubric_text, available_tools (Tool 정의 + mock_return)
  judge_prompt_templates
                    ↓
         LangGraph 파이프라인 실행
                    ↓
[C. API 수집] ─────────────────────────────────────────────
  model_responses: response_text / tool_call_output
  judge_raw_output: Knowledge + Agent
                    ↓
         노드별 처리 및 파싱
                    ↓
[D. 파이프라인 생성] ──────────────────────────────────────
  knowledge_scores_ab, _ba → _final (평균)
  agent_scores: call(코드 기반) + slot/relevance/completion(Judge)
  human_review_queue (선별 기준 충족 항목)
                    ↑
  [A 재주입] human_scores (담당자 검토) → judge_reliability 보정
                    ↓
  summary_table → pm_report_text
                    ↓
  eval_session_json (자동 저장 + 내보내기)
```

---

## 7. 유효성 검증 및 예외 처리 기준

| 상황 | 처리 방법 | 담당 위치 |
| --- | --- | --- |
| reference_answer 누락 | 입력 단계 차단. 필수 필드 안내 표시 | Screen 3 |
| instance_rubric 누락 | 입력 단계 차단. 입력 예시 가이드 표시 | Screen 3 |
| selected_models 1개 이하 | 입력 단계 차단. "2개 이상 선택" 안내 | Screen 4 |
| LLM API 호출 실패 | 최대 3회 자동 재시도. 초과 시 해당 모델 제외, 사용자 알림 | generate_responses |
| Judge JSON 파싱 실패 | retry_judge 노드 분기 (최대 3회). 실패 시 해당 항목 Human Review 큐 강제 포함 | validate_scores |
| Tool 호출 JSON 파싱 실패 | call_score=0 처리. raw_output 보존. Human Review 큐 포함 | evaluate_call |
| Tool 이름 불일치 | call_correct=False, call_score=0. 불일치 Tool 이름 기록 | evaluate_call |
| HyperCLOVA X / EXAONE API 접근 불가 | 해당 모델 제외 후 나머지로 진행. 결과에 "미포함" 명시 | generate_responses |
| Multi-turn 맥락 의존성 오류 | context_dependency 기반 검증 실패 시 해당 턴 별도 플래그 | evaluate_call |

---

## 8. 데이터 품질 보장 원칙

**원칙 1. instance_rubric 품질이 채점 전체 품질을 결정한다**
Judge 프롬프트에 직접 주입되므로 품질이 낮으면 채점 정밀도가 떨어진다.
UI에 구체적인 예시와 가이드를 표시하고, 등록 전 AI 품질 체크를 권장한다.

**원칙 2. Judge 원본 응답은 항상 보존한다**
파싱 후에도 raw_output을 EvalState에 유지한다.
파싱 오류 재시도 및 디버깅에 활용한다.

**원칙 3. Mock 반환값은 현실적인 데이터로 작성한다**
Tool 정의의 mock_return은 실제 업무에서 나올 법한 값으로 작성한다.
비현실적인 Mock 값은 completion 채점 품질을 저하시킨다.

**원칙 4. API 키는 코드에 직접 쓰지 않는다**
모든 API 키는 .env 파일로 관리하고 .gitignore에 추가한다.
model_config.yaml에는 환경변수 참조만 기재한다.

**원칙 5. 세션 스냅샷은 파이프라인 완료 시 항상 자동 저장한다**
평가 완료 후 /output/ 폴더에 자동 저장해 재실행 없이 결과 확인과 내보내기가 가능하게 한다.