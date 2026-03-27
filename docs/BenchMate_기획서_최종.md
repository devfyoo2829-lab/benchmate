# BenchMate — LLM 모델 평가 에이전트

# BenchMate 기획서

## Korean Enterprise LLM & Agent Evaluation Platform

> **"Your partner in picking the right LLM."**
기업이 LLM을 도입할 때, 지식 수준과 실제 업무 수행 능력(Agent)을 함께 평가해서 정량 점수로 비교하는 자동화 벤치마크 에이전트
> 

*작성일: 2026.03 | 작성자: 곽승연 | SeSAC LLM Agent 서비스 기획 최종 프로젝트*

---

## 하위 문서 목록

| 문서 | 설명 |
| --- | --- |
| [데이터 요구사항 문서] | 사용자 입력·시스템 구성·API 수집·파이프라인 생성 데이터 정의 |
| [데이터 구조 설계 문서] | EvalState, JSON 스키마, Tool 정의 구조 설계 |
| [시스템 워크플로우 다이어그램] | 전체 서비스 흐름 및 LangGraph 내부 흐름 시각화 |
| [Agent 설계 문서] | 에이전트 구성, 노드 정의, 분기 로직 설계 |

---

## 1. 문제 정의

### 1.1 배경

AI 도입을 검토하는 기업 실무 담당자 대부분은 AI 전문 지식이 없다. 산업 전반의 자동화 흐름을 인지하고 있으나, 어떤 LLM이 자사 업무에 적합한지 스스로 평가할 방법이 없다.

더 근본적인 문제는, 기업에서 LLM을 실제로 활용하는 방식이 단순한 질문-응답 수준이 아니라는 것이다. 내부 시스템 조회, 메일 작성, ERP·CRM 기능 호출 등 Tool 기반 업무 자동화가 실제 활용 형태다. 그런데 현재 시장의 LLM 평가 방식은 이를 전혀 반영하지 못한다.

### 1.2 기존 방식의 한계

| 구분 | 기존 방식 | 한계 |
| --- | --- | --- |
| 글로벌 벤치마크 | MMLU, HumanEval 등 | 영어 중심·범용 지식 평가. 한국어 실무 도메인 미반영 |
| 고정 루브릭 평가 | 모든 문항에 동일 기준 적용 | 문항별 핵심 포인트를 포착하지 못함 |
| 단순 Q&A 체감 테스트 | 담당자가 몇 가지 질문 던져보고 체감으로 판단 | 정량화 불가, 재현 불가, 비교 기준 없음 |
| 기존 Agent 평가 도구 | BFCL, FunctionChat 등 공개 벤치마크 | 고정 시나리오, 자사 도메인 맞춤 불가, 개발자 전용 |

### 1.3 핵심 문제 3가지

**문제 1. 기업은 LLM의 "지식"은 물어볼 수 있지만 "업무 수행 능력"은 평가할 수 없다**

LLM이 금융 용어를 알고 있어도, 실제로 `search_loan_rate(customer_id, credit_score)` 같은 Tool을 올바른 파라미터로 호출할 수 있는지는 전혀 다른 능력이다. 올거나이즈의 연구에서도 확인됐듯, 언어 능력이 뛰어난 LLM도 Tool calling의 구조화된 포맷(JSON) 출력에서는 실패하는 경우가 많다.

**문제 2. 평가 기준이 없어서 모델 간 정량 비교가 불가능하다**

현재 기업 담당자의 LLM 선택 근거는 "써보니 괜찮은 것 같다"는 수준에 머문다. 도입 후 ROI 예측도, 모델 교체 근거도 만들 수 없다.

**문제 3. 기존 평가 도구는 비전문가가 사용하기 어렵다**

공개 벤치마크 도구들은 개발자 전용이고, 고정된 시나리오만 지원한다. 기업 담당자가 "우리 회사 실제 업무 질문"으로 직접 평가를 돌릴 수 있는 도구가 없다.

---

## 2. 해결 전략

### 2.1 핵심 아이디어

> 담당자가 **이미 정답을 알고 있는 업무 질문**을 입력하면,
BenchMate가 여러 LLM에게 동일한 질문을 던지고,
Knowledge(지식)와 Agent(Tool calling) 두 축으로 자동 채점해서
정량 점수와 PM 해석 리포트를 출력한다.
> 

### 2.2 평가 구조 — 두 축 분리 측정

| 축 | 평가 모드 | 무엇을 측정하나 | 채점 방식 |
| --- | --- | --- | --- |
| **Knowledge** | 지식·응답 품질 | 정확성, 한국어 자연성, 할루시네이션, 도메인 전문성, 응답 적절성 | Qwen 2.5 Judge (LLM-as-a-Judge) |
| **Agent** | Tool calling 능력 | call(Tool 선택·파라미터), slot(되묻기), relevance(거절), completion(요약) | call: 코드 기반 JSON 비교 / 나머지: Qwen 2.5 Judge |

두 점수를 2축 매트릭스로 시각화하면 "지식은 높지만 Tool calling이 약한 모델"과 같은 패턴이 가시화된다. 이것이 기존 벤치마크와 가장 명확하게 차별화되는 지점이다.

### 2.3 Judge 모델 선택 — Qwen 2.5

피평가 모델 5개(Solar Pro, GPT-4o, Claude Sonnet, HyperCLOVA X, EXAONE)와 이해충돌이 없는 외부 모델을 Judge로 써야 한다. Qwen 2.5-32B를 선택한 이유:

- 피평가 대상 모델과 이해충돌 없음
- 오픈소스 — 채점 로직 블랙박스 아님, 투명성 확보
- KMMLU(한국어) 공식 측정, JSON 출력 안정성 검증
- API 비용 없음 (HuggingFace 또는 로컬 실행)

단, Qwen 2.5는 한국 업무 도메인 특화 Judge가 아니므로 Human Review로 신뢰도를 보정한다.

### 2.4 Instance-Specific Rubric — BiGGen Bench 방법론 차용

BiGGen Bench(NAACL 2025 Best Paper, LG AI Research)의 핵심 방법론을 경량화해서 적용한다. 모든 문항에 동일한 루브릭을 적용하는 대신, 문항 등록 시 "이 문항에서 특히 봐야 할 핵심 채점 포인트"를 함께 입력받아 Judge 프롬프트에 주입한다.

```
[기존 방식]
모든 문항: 정확성 / 자연성 / 할루시네이션 / 전문성 / 적절성 — 동일 기준

[Instance-Specific Rubric 방식]
"신용대출 금리 3가지 설명" 문항:
→ "COFIX, 신용등급, 가산금리 세 가지를 모두 언급했는가?"
→ "각 요소가 금리에 미치는 방향(정비례/반비례)을 명시했는가?"
```

### 2.5 call 항목 코드 기반 채점

Agent 평가의 call 항목(Tool 선택 + 파라미터 생성)은 LLM Judge 없이 코드로 채점한다. 정답 Tool 이름과 파라미터를 JSON으로 파싱해서 모델 출력과 직접 비교하므로 Judge 편향이 없다.

---

## 3. 구체적인 실행 방안

### 3.1 구현 범위

**In-Scope (이번 버전)**

- 5개 사전 정의 도메인 기반 문항 입력 UI
- 멀티 모델 동시 응답 수집 (최대 5개 모델)
- Knowledge 모드: Qwen 2.5 Judge + Instance-Specific Rubric 자동 채점
- Agent 모드: Single-turn(Type A/B/C) + Multi-turn(5턴) 평가
- call 항목 코드 기반 채점 (JSON 파싱 비교)
- Position Bias 제거 (A↔B 교차 평가)
- Human Review 인터페이스 (채점 검토·수정)
- 결과 시각화 대시보드 (Knowledge vs Agent 매트릭스 포함)
- PM 해석 리포트 자동 생성
- LangGraph End-to-End 파이프라인
- Streamlit 7-Screen 웹 데모

**Out-of-Scope (이번 버전 제외)**

- 커스텀 도메인 문서 업로드
- 사용자 계정·인증 시스템
- 평가 이력 DB 저장 및 버전 관리
- API 외부 제공
- Real Execution (실제 Tool 연결)
- 한국어 Judge 모델 파인튜닝

### 3.2 도메인 및 Tool 구성

**사전 정의 5개 도메인**

| 도메인 | 태스크 유형 | 기본 Tool 예시 |
| --- | --- | --- |
| 금융 | 대출 심사, 금융상품 비교, 수치 계산 | `search_loan_rate`, `calculate_interest`, `get_product_info` |
| 법률·규정 | 계약서 해석, 규정 준수, 법률 용어 | `search_regulation`, `check_compliance`, `get_contract_template` |
| 인사·HR | 취업규칙 해석, 성과 피드백, 채용 공고 | `search_hr_policy`, `get_employee_info`, `create_feedback_draft` |
| 고객응대·CS | 민원 응답, FAQ 생성, 감정 분석 | `search_faq`, `get_customer_history`, `create_response_draft` |
| 제조·기술문서 | 매뉴얼 요약, 불량 분석, 기술 번역 | `search_manual`, `get_defect_history`, `translate_technical_term` |

### 3.3 Agent 평가 시나리오 설계

**Single-turn — 3가지 유형**

| 유형 | 상황 | 기대 동작 | 평가 항목 |
| --- | --- | --- | --- |
| Type A | 정보 충분, 정상 호출 | 올바른 Tool + 올바른 파라미터 호출 | call |
| Type B | 정보 부족 → 되묻기 필요 | "고객 ID를 알려주시겠어요?" | slot |
| Type C | 불가능한 요청 | "해당 Tool이 없습니다" 거절 | relevance |

**Multi-turn — 5턴 체인 구조**

```
Turn 1: 사용자 요청 → Tool 호출 1 (call)
Turn 2: Mock 결과 반환 → Tool 호출 2 (Turn 1 결과 활용, 맥락 유지)
Turn 3: Mock 결과 반환 → 자연어 요약 (completion)
Turn 4: 사용자 추가 요청 → Tool 호출 3 (이전 맥락 기억 필요)
Turn 5: Mock 결과 반환 → 최종 응답
```

추가 측정: 맥락 유지율 / 불필요한 재질문 없음 / Tool 체인 정확도

### 3.4 Human Review 설계

Human Review 큐 자동 선별 기준:

- call 점수 0점 (완전 실패) 또는 Judge 교차 평가 점수 편차 ≥ 3점
- hallucination 점수 ≤ 2점
- 전체 문항의 랜덤 20% 샘플

담당자 검토 후 Judge-Human 일치율을 신뢰도 지표로 기록한다.

### 3.5 결과 시각화 구성

| 차트 | 내용 |
| --- | --- |
| Knowledge vs Agent 매트릭스 | 2축 산점도 — 괴리 시각화 (핵심 차별점) |
| Tool calling 세부 항목 바 차트 | call / slot / relevance / completion 모델 비교 |
| Knowledge 레이더 차트 | 5축 기준 모델별 비교 |
| Multi-turn 히트맵 | 턴별 × 모델별 Tool 정확도 |
| 지표 카드 | 종합 추천 모델, 할루시네이션 최저 모델, Judge 신뢰도 |

### 3.6 전체 서비스 흐름 (7 Screen)

```
Screen 1: 평가 모드 선택 (Knowledge / Agent / 통합)
Screen 2: 도메인 선택 + Tool 확인 (사전 Tool 로드)
Screen 3: 시나리오 구성
          [Knowledge] 질문 + 정답 + 핵심 채점 포인트
          [Agent Single] 유형(A/B/C) + 정답 Tool 등록
          [Agent Multi] 턴별 흐름 + 기대 동작 등록
Screen 4: 모델 선택 + 파이프라인 실행 (진행률 표시)
Screen 5: 결과 대시보드
Screen 6: Human Review (채점 검토·수정)
Screen 7: PM 해석 리포트 + 내보내기
```

### 3.7 기술 스택

| 구성 요소 | 기술 | 선택 이유 |
| --- | --- | --- |
| 파이프라인 | LangGraph | 조건부 분기, Multi-turn 루프, 상태 관리 |
| 실험 추적 | LangSmith | 턴별 호출 이력, 디버깅 |
| Judge 모델 | Qwen 2.5-32B | 이해충돌 없음, 한국어, 오픈소스 |
| call 채점 | Python 코드 (JSON 비교) | Judge 편향 없는 구조적 측정 |
| 피평가 모델 | Solar Pro, GPT-4o, Claude Sonnet, HyperCLOVA X, EXAONE | 한국 Enterprise 주요 후보 |
| UI | Streamlit (7 Screen) | LangGraph 직접 연동, 빠른 구현 |
| Tool 실행 | Mock JSON (Simulated) | 데모 단계 |

---

## 4. Trade-off 및 리스크

### 4.1 설계 Trade-off

**① Qwen 2.5 단독 Judge vs 앙상블 Judge**

| 항목 | Qwen 2.5 단독 | 앙상블 (복수 Judge) |
| --- | --- | --- |
| 채점 일관성 | 낮음 (단일 모델 편향) | 높음 (편향 상쇄) |
| 비용·복잡도 | 낮음 | 높음 |
| 한국어 특화 | 미검증 | 미검증 (동일 문제) |
| **선택** | ✅ 선택 (Human Review로 보완) | — |

단일 Judge의 신뢰도 한계를 Human Review 인터페이스로 보완하는 구조로 결정했다. 추후 다중 Judge 앙상블은 로드맵으로 남긴다.

**② Instance-Specific Rubric vs 고정 루브릭**

| 항목 | 고정 루브릭 | Instance-Specific Rubric |
| --- | --- | --- |
| 구현 복잡도 | 낮음 | 중간 (문항 등록 UI 필드 추가) |
| 채점 정밀도 | 낮음 | 높음 |
| 담당자 부담 | 낮음 | 약간 높음 (포인트 입력 필요) |
| **선택** | — | ✅ 선택 (BiGGen Bench 방법론 근거) |

구현 난이도 대비 채점 품질 향상 효과가 크고, 담당자가 입력하는 포인트 자체가 "정말 어떤 능력을 평가하려는가"를 명확히 하는 기획 도구로도 작동한다.

**③ Simulated Tool vs Real Execution**

| 항목 | Simulated (Mock) | Real Execution |
| --- | --- | --- |
| 구현 난이도 | 낮음 | 높음 (실제 API 연결, 인증) |
| 평가 현실성 | 낮음 (Mock 결과) | 높음 |
| 데모 가능성 | 높음 | 낮음 (연결 불안정 리스크) |
| **선택** | ✅ 선택 (데모 단계) | 로드맵 |

데모 목적에서는 LLM이 올바른 Tool을 선택하고 올바른 파라미터를 생성하는지를 평가하는 것으로 충분하다. Mock 반환값을 사전에 정의해두면 Tool 결과 처리 능력도 함께 평가 가능하다.

**④ Single-turn만 vs Single + Multi-turn**

| 항목 | Single-turn만 | Single + Multi-turn |
| --- | --- | --- |
| 구현 복잡도 | 낮음 | 높음 (LangGraph 루프, 맥락 관리) |
| 실제 업무 반영도 | 낮음 | 높음 |
| 평가 항목 풍부도 | 낮음 | 높음 |
| **선택** | — | ✅ 선택 |

B2B 업무는 실제로 다턴 대화 흐름을 갖는다. Single-turn만으로는 실제 도입 후 성능을 예측하기 어렵다.

### 4.2 주요 리스크 및 대응

**R1. Qwen 2.5의 한국어 도메인 채점 신뢰도**

- 리스크: KMMLU 점수는 지식 측정이지, 채점 능력 측정이 아님. 한국 금융·법률 도메인의 미묘한 표현을 Judge가 잘못 채점할 수 있음.
- 영향도: 높음 (핵심 기능의 신뢰도 문제)
- 대응: Human Review 인터페이스로 Judge-Human 일치율을 투명하게 공개. 불일치율이 높은 도메인은 별도 표시.

**R2. call 항목 채점의 파라미터 유연성 문제**

- 리스크: 정답과 동일한 의미지만 형식이 다른 경우 (예: `"customer_id": "C-1234"` vs `"customerId": "C-1234"`) 코드 비교에서 오답으로 판정될 수 있음.
- 영향도: 중간
- 대응: 파라미터 비교 시 키 정규화(snake_case 통일), 값 타입 캐스팅 로직 포함. 완전 일치 외에 "의미적 일치" 점수 부분점수 부여 방안 검토.

**R3. Multi-turn 맥락 관리 복잡도**

- 리스크: LangGraph Multi-turn 루프에서 이전 Turn 정보가 EvalState에 올바르게 전달되지 않아 맥락이 끊길 수 있음.
- 영향도: 중간
- 대응: conversation_history를 EvalState에 명시적으로 관리. LangSmith로 턴별 상태 추적. 3턴 이상 시나리오는 파일럿 테스트 후 도입.

**R4. HyperCLOVA X / EXAONE API 접근 불가**

- 리스크: 두 모델은 API 접근이 제한적이거나 조건부.
- 영향도: 낮음 (비교군 축소)
- 대응: Solar Pro, GPT-4o, Claude Sonnet 3개 모델로 핵심 비교 구성. HyperCLOVA X / EXAONE는 접근 가능 시 추가.

**R5. Position Bias 제거의 비용**

- 리스크: A→B, B→A 교차 평가 시 Judge 호출 횟수가 2배. 문항 수 × 모델 수 × 2회.
- 영향도: 중간 (실행 시간 증가)
- 대응: 병렬 비동기 처리(asyncio)로 속도 최적화. Knowledge 모드에서만 교차 평가 적용, Agent call 항목은 코드 기반이라 불필요.

---

## 5. 타깃 사용자

### Persona A — 기업 AX/DX 담당자

| 항목 | 내용 |
| --- | --- |
| AI 지식 수준 | 낮음. ChatGPT 정도 사용 경험 |
| 핵심 목표 | "우리 회사 업무에 맞는 LLM"을 근거 있는 데이터로 선택 |
| 성공 기준 | "A 모델이 금융 업무에서 B 모델보다 23% 더 정확하다"는 한 문장 |

### Persona B — 파운데이션 모델 PM / 엔지니어

| 항목 | 내용 |
| --- | --- |
| AI 지식 수준 | 높음. 자체 벤치마크 방법론 보유 |
| 핵심 목표 | 특정 도메인 성능을 빠르게 검증. 기존 내부 벤치마크의 보조 도구로 활용 |
| 성공 기준 | 새 도메인 평가를 30분 안에 돌릴 수 있는가 |

---

## 6. 차별점

| 비교 대상 | BenchMate 차별점 |
| --- | --- |
| 글로벌 벤치마크 (MMLU 등) | 영어·지식 중심 → 한국어 + 실무 Tool calling 포함 |
| BiGGen Bench | 연구용 대규모 고정 데이터셋 → 경량화·커스텀화, 기업 담당자 직접 사용 가능 |
| 올거나이즈 평가 플랫폼 | 모델 개발용(내부) → LLM 도입 의사결정용(구매자), 개발자 전용 → 비전문가 사용 가능 |
| 단순 Q&A 평가 | 지식만 측정 → Knowledge + Agent 두 축 분리 + 괴리 시각화 |

---

## 7. 미결 사항

- [ ]  금융 도메인 시드 문항 10개 직접 작성 (질문 + 정답 + 핵심 채점 포인트)
- [ ]  Instance-Specific Rubric 주입 Judge 프롬프트 설계 + 파일럿 테스트 (5문항)
- [ ]  call 항목 파라미터 정규화 규칙 확정 (키 형식, 타입 캐스팅 범위)
- [ ]  Multi-turn 시나리오 1개 완성 후 LangGraph 루프 파일럿 테스트
- [ ]  HyperCLOVA X / EXAONE API 접근 방법 확인
- [ ]  Mock 반환값 JSON 스키마 확정
- [ ]  CLAUDE.md 작성 후 Claude Code 개발 착수

---

*참고 방법론: BiGGen Bench (NAACL 2025 Best Paper, LG AI Research), 올거나이즈 LLM 평가 플랫폼 (2025.02), Prometheus 2 (EMNLP 2024), MT-Bench (NeurIPS 2023)*

[데이터 요구사항 정의서](https://www.notion.so/330f9740b775806ca736f9b5700867f9?pvs=21)

[데이터 구조 설계](https://www.notion.so/330f9740b77580d0a2f0c9f2b8f4096b?pvs=21)

[시스템 워크플로우 다이어그램](https://www.notion.so/330f9740b775808d80c6ea1b87a1fd99?pvs=21)

[Agent 설계서](https://www.notion.so/Agent-330f9740b775800285c9df2ab4f4f30b?pvs=21)