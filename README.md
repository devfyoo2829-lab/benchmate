# BenchMate
### Korean Enterprise LLM & Agent Evaluation Platform

> 기업이 LLM을 도입할 때, **지식 수준(Knowledge)**과 **실제 업무 수행 능력(Agent)**을
> 함께 평가해서 정량 점수로 비교하는 자동화 벤치마크 에이전트

*SeSAC LLM Agent 서비스 기획 최종 프로젝트 | 2026.03*

---

## 배경 및 문제 정의

AI 도입을 검토하는 기업 실무 담당자 대부분은 어떤 LLM이 자사 업무에 적합한지 **스스로 평가할 방법이 없다**.

기존 평가 방식의 한계:

| 방식 | 한계 |
|---|---|
| MMLU 등 글로벌 벤치마크 | 영어 중심·범용 지식 평가, 한국어 실무 미반영 |
| 단순 Q&A 체감 테스트 | 정량화 불가, 재현 불가, 비교 기준 없음 |
| 기존 Agent 평가 도구 | 고정 시나리오, 자사 도메인 맞춤 불가, 개발자 전용 |

특히 기업에서 LLM을 실제로 활용하는 방식은 단순 질문-응답이 아니라 **Tool 기반 업무 자동화**다. 언어 능력이 뛰어난 LLM도 Tool 호출의 구조화된 JSON 출력에서 실패하는 경우가 많다(올거나이즈, 2025).

---

## 핵심 아이디어

담당자가 **이미 정답을 알고 있는 업무 질문**을 입력하면,
BenchMate가 여러 LLM에게 동일한 질문을 던지고,
**Knowledge**와 **Agent** 두 축으로 자동 채점해서
정량 점수와 PM 해석 리포트를 출력한다.

```
사용자 입력 (질문 + 정답 + 핵심 채점 포인트)
        ↓
LangGraph 파이프라인 자동 실행
        ↓
Knowledge 점수 × Agent 점수 2축 매트릭스
        ↓
"A 모델은 금융 지식은 우수하지만 Tool 파라미터 정확도가 낮아
 텍스트 생성 업무에 적합합니다." — PM 해석 리포트 자동 생성
```

---

## 평가 구조

### Knowledge 평가

- **채점 방식**: Qwen 2.5-32B Judge (LLM-as-a-Judge)
- **방법론**: Instance-Specific Rubric (BiGGen Bench, NAACL 2025 Best Paper 차용)
  - 모든 문항에 동일한 기준을 적용하는 대신, **문항마다 고유한 핵심 채점 포인트**를 Judge 프롬프트에 주입
- **채점 축**: 정확성 · 한국어 자연성 · 할루시네이션 · 도메인 전문성 · 응답 적절성
- **Position Bias 제거**: A→B, B→A 교차 채점 후 평균

### Agent 평가

- **채점 방식**: call 항목은 **코드 기반 JSON 비교**, 나머지는 Qwen 2.5 Judge
- **방법론**: 올거나이즈 LLM 평가 플랫폼 4축 차용
- **채점 축**:

| 항목 | 설명 | 채점 방식 |
|---|---|---|
| call | Tool 이름 + 파라미터 정확도 | 코드 (Judge 편향 없음) |
| slot | 정보 부족 시 적절히 되묻기 | Qwen 2.5 Judge |
| relevance | 불가능한 요청 적절히 거절 | Qwen 2.5 Judge |
| completion | Tool 결과를 자연어로 요약 | Qwen 2.5 Judge |

- **시나리오 유형**: Single-turn (Type A/B/C) + Multi-turn (5턴 체인)

### Judge 모델: Qwen 2.5-32B 선택 이유

피평가 5개 모델(Solar Pro, GPT-4o, Claude Sonnet, HyperCLOVA X, EXAONE)과 **이해충돌이 없는** 외부 모델 필요 → 오픈소스, KMMLU 한국어 공식 지원, JSON 출력 안정성 검증

---

## 평가 도메인

| 도메인 | 주요 태스크 | Tool 예시 |
|---|---|---|
| 금융 | 대출 심사, 금융상품 비교, 수치 계산 | `search_loan_rate`, `calculate_interest` |
| 법률·규정 | 계약서 해석, 규정 준수 | `search_regulation`, `check_compliance` |
| 인사·HR | 취업규칙 해석, 성과 피드백 | `search_hr_policy`, `create_feedback_draft` |
| 고객응대·CS | 민원 응답, FAQ 생성 | `search_faq`, `create_response_draft` |
| 제조·기술문서 | 매뉴얼 요약, 불량 분석 | `search_manual`, `get_defect_history` |

---

## 기술 스택

| 구성 요소 | 기술 |
|---|---|
| 파이프라인 | LangGraph (StateGraph, 조건부 분기, 상태 관리) |
| 실험 추적 | LangSmith |
| Judge 모델 | Qwen 2.5-32B (HuggingFace) |
| 피평가 모델 | Solar Pro · GPT-4o · Claude Sonnet · HyperCLOVA X · EXAONE |
| UI | Streamlit (7 Screen) |
| Tool 실행 | Simulated Mock (데모 단계) |
| 언어 | Python 3.11+ |

---

## 시스템 아키텍처

```
[Streamlit UI — 7 Screen]
  Screen 1: 평가 모드 선택 (Knowledge / Agent / 통합)
  Screen 2: 도메인 + Tool 설정
  Screen 3: 시나리오 구성 (질문 + 정답 + 핵심 채점 포인트)
  Screen 4: 모델 선택 + 파이프라인 실행
  Screen 5: 결과 대시보드 (Knowledge vs Agent 2축 매트릭스)
  Screen 6: Human Review (채점 결과 검토 · 수정)
  Screen 7: PM 해석 리포트 + 내보내기

[LangGraph 파이프라인]
  load_scenarios → route_mode
    → [Knowledge] generate_responses → judge_knowledge
    → [Agent]     generate_tool_calls → evaluate_call → judge_agent
    → validate_scores → flag_human_review
    → aggregate_results → generate_report → END
```

---

## 실행 방법

### 1. 의존성 설치

```bash
pip install -r requirements.txt
```

### 2. 환경변수 설정

`.env` 파일 생성 후 API 키 입력:

```
UPSTAGE_API_KEY=your_key
OPENAI_API_KEY=your_key
ANTHROPIC_API_KEY=your_key
HF_TOKEN=your_key
LANGSMITH_API_KEY=your_key
```

### 3. 실행

```bash
streamlit run app.py
```

---

## 프로젝트 구조

```
benchmate/
├── app.py                    # Streamlit 진입점
├── CLAUDE.md                 # Claude Code 프로젝트 설명
├── pipeline/
│   ├── state.py              # EvalState TypedDict (중앙 상태)
│   ├── graph.py              # LangGraph 그래프 조립
│   └── nodes/                # 노드 함수 10개
├── data/
│   ├── questions/            # 도메인별 평가 문항 JSON
│   ├── tools/                # 도메인별 Tool 정의 + Mock 반환값
│   └── scenarios/            # Agent 평가 시나리오 JSON
├── prompts/                  # Judge 프롬프트 Jinja2 템플릿
├── ui/                       # Streamlit 화면 (screen1~7.py)
├── evaluators/               # call 항목 코드 기반 채점 로직
├── output/                   # 평가 세션 결과 JSON (자동 저장)
└── tests/
```

---

## 차별점

| 비교 대상 | BenchMate |
|---|---|
| 글로벌 벤치마크 | 영어·지식 중심 → **한국어 + 실무 Tool calling 포함** |
| BiGGen Bench | 연구용 대규모 고정 데이터셋 → **경량화·커스텀화, 비전문가 사용 가능** |
| 올거나이즈 평가 플랫폼 | 모델 개발용(내부) → **LLM 도입 의사결정용(구매자)** |
| 단순 Q&A 평가 | 지식만 측정 → **Knowledge + Agent 괴리 시각화** |

---

## 참고 방법론

- BiGGen Bench — NAACL 2025 Best Paper, LG AI Research
- 올거나이즈 LLM 평가 플랫폼 — Tool calling 4축 평가 방법론 (2025.02)
- Prometheus 2 — EMNLP 2024
- MT-Bench — NeurIPS 2023

---

*작성자: 곽승연 | SeSAC AI 서비스 기획 과정*