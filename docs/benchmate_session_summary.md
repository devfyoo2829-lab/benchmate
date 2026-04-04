# BenchMate 개발 세션 요약

**Korean Enterprise LLM & Agent Evaluation Platform**
작성일: 2026-04-02 | 작성자: 곽승연 | SeSAC LLM Agent 서비스 기획 최종 프로젝트
GitHub: https://github.com/devfyoo2829-lab/benchmate

---

## 1. 프로젝트 개요

BenchMate는 기업이 LLM 도입 시 **지식 수준(Knowledge)**과 **실제 업무 수행 능력(Agent)**을 함께 평가하여 정량 점수로 비교하는 자동화 벤치마크 에이전트입니다.

담당자가 이미 정답을 알고 있는 업무 질문을 입력하면, BenchMate가 여러 LLM에게 동일한 질문을 던지고 자동 채점하여 PM 해석 리포트를 출력합니다.

| 항목 | 내용 |
|---|---|
| 평가 모드 | Knowledge / Agent / 통합(Integrated) |
| 피평가 모델 | Solar Pro · GPT-4o · Claude Sonnet (claude-sonnet-4-5) |
| Judge 모델 | GPT-4o-mini (구 Qwen 2.5-7B → HF 무료 티어 한계로 교체) |
| 평가 도메인 | 금융 (법률·인사·CS·제조 — RAG 추가 시 자동 활성화 예정) |
| 기술 스택 | LangGraph · Streamlit · Supabase · reportlab · plotly |

---

## 2. 시스템 아키텍처

**"심사위원단이 수험생들을 채점하는 구조"** — 멀티 에이전트

| 구성 요소 | 역할 | 담당 모델/기술 |
|---|---|---|
| 피평가자 (×N) | 질문 답변 · Tool 호출 | Solar Pro / GPT-4o / Claude Sonnet |
| Judge (채점자) | 응답 채점 (5축 루브릭) | GPT-4o-mini |
| 코드 채점기 | Tool 호출 JSON 비교 | Python (편향 없음) |
| 리포트 작성자 | PM 해석 보고서 생성 | GPT-4o |
| 파이프라인 | 상태 관리 · 분기 · 재시도 | LangGraph StateGraph |
| DB | 평가 이력 저장 | Supabase PostgreSQL (6개 테이블) |

### 아키텍처 분류
- **멀티 에이전트**: 피평가자 / Judge / 리포트 작성자 역할 분리
- **조건부 라우팅**: `decide_branch()` — Knowledge / Agent / Integrated 분기
- **재시도 루프**: `decide_retry()` — Judge JSON 파싱 실패 시 최대 3회 재시도
- **Human-in-the-loop**: Screen 6에서 담당자 직접 개입
- **검색 없음**: LLM 자체 능력 측정이 목적 (RAG는 문항 자동 생성용으로만 추가 예정)

---

## 3. LangGraph 파이프라인 — 11개 노드

```
load_scenarios → route_mode
    ↓ Knowledge                    ↓ Agent
generate_responses          generate_tool_calls
judge_knowledge              evaluate_call
    ↓                              judge_agent
validate_scores ←─── 재시도 루프 (최대 3회)
flag_human_review
aggregate_results
generate_report → END
```

| 노드 | 역할 | 상태 |
|---|---|---|
| `load_scenarios` | JSON 로드 · 세션 초기화 | ✅ |
| `route_mode` | Knowledge / Agent 분기 | ✅ |
| `generate_responses` | 멀티모델 비동기 병렬 호출 | ✅ |
| `generate_tool_calls` | Tool 호출 응답 수집 | ✅ |
| `judge_knowledge` | GPT-4o-mini Judge · A↔B 교차 채점 | ✅ |
| `evaluate_call` | 코드 기반 JSON 비교 채점 | ✅ |
| `judge_agent` | slot · relevance · completion 채점 | ✅ |
| `validate_scores` | JSON 파싱 검증 · 재시도 ×3 | ✅ |
| `flag_human_review` | 4가지 기준 선별 · 랜덤 20% | ✅ |
| `aggregate_results` | ab/ba 평균 · 비용 집계 | ✅ |
| `generate_report` | PM 리포트 · 세션 JSON 저장 | ✅ |

---

## 4. 평가 방법론

### Knowledge 평가
- **채점 방식**: GPT-4o-mini Judge (LLM-as-a-Judge)
- **방법론**: Instance-Specific Rubric — 문항마다 고유한 핵심 채점 포인트 주입 (BiGGen Bench, NAACL 2025)
- **Position Bias 제거**: A→B, B→A 교차 채점 후 평균

| 채점 축 | 만점 |
|---|---|
| 사실 정확도 | 5점 |
| 한국어 자연성 | 5점 |
| 허위정보 없음 | 5점 |
| 도메인 전문성 | 5점 |
| 응답 적절성 | 5점 |
| **합계** | **25점** |

### Agent 평가

| 항목 | 채점 방식 | 비고 |
|---|---|---|
| call (Tool 호출 정확도) | 코드 기반 JSON 비교 | Judge 편향 없음 |
| slot (정보 부족 시 되묻기) | GPT-4o-mini Judge | single_B 시나리오 |
| relevance (불가 요청 거절) | GPT-4o-mini Judge | single_C 시나리오 |
| completion (결과 요약 품질) | GPT-4o-mini Judge | single_A 시나리오 |

---

## 5. Streamlit UI — 7 Screen

| Screen | 화면명 | 주요 기능 |
|---|---|---|
| 1 | 평가 모드 선택 | Knowledge / Agent / 통합 카드 선택 |
| 2 | 도메인 선택 | 5개 도메인 카드 + 사내 기능 직접 추가 |
| 3 | 시나리오 구성 | 문항 입력 + 예시 채우기 + Agent 시나리오 등록 |
| 4 | 평가 실행 | 모델 선택 + 파이프라인 실행 + 진행 상태 표시 |
| 5 | 결과 대시보드 | 레이더 차트 · 바 차트 · 포지셔닝 매트릭스 · Agent 히트맵 |
| 6 | Human Review | AI 채점 검토 · 담당자 점수 수정 · Judge 신뢰도 계산 |
| 7 | PM 리포트 | 매킨지 스타일 1페이지 PDF + 차트 포함 |

### UX 설계 원칙
- 모든 기술 용어를 비기술 담당자 눈높이로 표현 (knowledge → "도메인 지식 평가")
- 예시 채우기 버튼으로 입력 허들 최소화
- 오류 발생 시 사용자 친화적 안내 메시지 표시
- 크레딧 소진 / 모델명 오류 / HF 서버 오류 구분 안내

---

## 6. Supabase DB 스키마 (6개 테이블)

```sql
eval_sessions     -- 평가 세션 기본 정보
model_responses   -- 모델별 응답 원문 + 토큰 수
knowledge_scores  -- Knowledge 채점 결과 (ab/ba/final)
agent_scores      -- Agent 채점 결과
human_reviews     -- Human Review 검토 결과
eval_reports      -- PM 리포트 텍스트
```

- 모든 테이블 `session_id` 기준 외래키 + 인덱스
- `ON DELETE CASCADE` — 세션 삭제 시 하위 데이터 자동 삭제
- RLS 비활성화 (개발 단계)

---

## 7. E2E 테스트 결과

| 테스트 | 결과 | 비고 |
|---|---|---|
| tool_call_evaluator 단위 테스트 | ✅ 29/29 통과 | JSON 비교 · 타입 캐스팅 |
| Knowledge E2E (Solar Pro) | ✅ fin_001 total=22/25 | 실제 Solar API 호출 |
| Agent E2E (Solar Pro) | ✅ call=1, completion=3 | Mock Tool 호출 |
| LangGraph Studio 연동 | ✅ 전 노드 통과 | `langgraph dev` |
| Supabase DB 저장 | ✅ 6개 테이블 확인 | eval_sessions 등 |

---

## 8. 기술 스택 현황

| 기술 | 상태 | 용도 |
|---|---|---|
| LangGraph | ✅ 사용 | 파이프라인 핵심 — StateGraph · 조건부 분기 · 재시도 루프 |
| Tool / Agent | ✅ 사용 | Agent 평가 시나리오 · Tool 정의 · 코드 채점 |
| 외부 API | ✅ 사용 | Solar Pro · GPT-4o · Claude · GPT-4o-mini (Judge) |
| Streamlit | ✅ 사용 | 7 Screen Web UI |
| Supabase | ✅ 사용 | 평가 이력 저장 (6개 테이블) |
| LangSmith | ✅ 사용 | 파이프라인 실행 추적 |
| LangChain | ⬜ 예정 | RAG 문항 자동 생성 시 추가 |
| RAG / Vector DB | ⬜ 예정 | 사내 문서 → 문항 자동 생성 |
| n8n | ⬜ 예정 | 평가 완료 → Slack 알림 · 정기 스케줄링 |
| 커스텀 에이전트 평가 | ⬜ 예정 | URL 입력 → 수업 에이전트 평가 |

---

## 9. 데이터 파일 구조

```
data/
├── questions/
│   └── finance.json          # 금융 평가 문항 3개 (fin_001~003)
├── tools/
│   └── finance_tools.json    # search_loan_rate, calculate_interest
├── scenarios/
│   └── finance_scenarios.json # 7개 시나리오 (single_A×2, B×2, C×2, multi×1)
└── pricing.json              # 모델별 API 단가 (USD per 1k tokens)
```

---

## 10. PDF 리포트 (Screen 7)

### 구성 (1페이지, A4)
1. 헤더 — BenchMate 로고 + 문서번호/평가일/도메인
2. KPI 4개 박스 — 추천 모델 · 최고 지식점수 · 비용 효율 최고 · Judge 신뢰도
3. Knowledge 5축 레이더 차트
4. Knowledge 총점 가로 바 차트
5. 핵심 발견 (1줄 요약)
6. 강점 분석 · 리스크 & 권고 (2컬럼)
7. 모델 비교 표 (지식총점 · 정확도 · 허위정보 · 전문성 · Tool호출 · 슬롯 · 거절 · 완료 · USD · KRW)
8. 푸터

### 색상 시스템
- Primary: `#1A1A1A` (블랙톤)
- 강조 1: `#2563EB` (블루 — 헤더, 추천 모델)
- 강조 2: `#F59E0B` (앰버 — 최고값 셀)
- 위험: `#EF4444` (허위정보 점수 ≤2 셀)
- 폰트: AppleSDGothicNeo (Mac) / 폴백 기본 폰트

---

## 11. 주요 설계 결정

| 결정 | 내용 |
|---|---|
| Judge 모델 | Qwen 2.5-32B → 7B → GPT-4o-mini (HF 무료 티어 한계) |
| call 채점 | 코드 기반 JSON 비교 (Judge 없음 — 편향 방지) |
| Position Bias | A→B, B→A 교차 채점 후 평균 (Knowledge만) |
| Tool 실행 | Simulated Mock (데모 단계) |
| 도메인 구분 | 금융만 활성화 / 나머지는 RAG 추가 시 자동 활성화 |
| 비용 표시 | USD + KRW (환율 1,380 적용) |

---

## 12. 주요 버그 수정 이력

- `state.py`: NotRequired 적용 → LangGraph Studio Required 필드 문제 해결
- `load_scenarios.py`: finance.json dict 구조 → List 할당 버그 수정 (`["questions"]` 추출)
- `generate_responses.py`: `"claude-sonnet"` → `"claude-sonnet-4-5"` 모델명 매핑 (`_resolve_model_name()`)
- 전체 노드: `asyncio.run()` → `nest_asyncio + new_event_loop()` (Streamlit 충돌 해결)
- reportlab: `pt` import 제거 (v4.4.10 호환)
- PDF 차트: `ImageReader` → tempfile 임시 저장 후 경로로 삽입
- Judge 모델: Qwen2.5-32B → 7B → GPT-4o-mini (HF 무료 티어 한계)
- 통합 모드: `_integrated_phase` Knowledge→Agent 전환 로직 수정
- Human Review: Streamlit 중첩 딕셔너리 직접 수정 → 전체 교체 방식으로 변경

---

## 13. 다음 단계 로드맵

### Phase 1 — RAG + LangChain
- 사내 문서 업로드 (PDF/DOCX)
- LangChain Document Loader + TextSplitter 3종 (고정 크기 / 의미 단위 / 계층형)
- Supabase pgvector 임베딩 저장
- 도메인 자동 감지 + 문항 자동 생성
- 법률/인사/CS/제조 도메인 자동 활성화

### Phase 2 — n8n 자동화
- 평가 완료 → Slack 알림
- 정기 평가 스케줄링

### Phase 3 — 커스텀 에이전트 평가
- URL 입력 → 수업에서 만든 에이전트 평가 지원
- (Cartells, LangGraph Telegram 날씨 에이전트 등)
- BenchMate가 단순 LLM 비교 도구 → 범용 벤치마크 플랫폼으로 확장

---

## 14. 환경 설정

```bash
# 가상환경
uv venv --python 3.13
source .venv/bin/activate

# 패키지 설치
uv pip install -r requirements.txt

# 실행
.venv/bin/python -m streamlit run app.py

# LangGraph Studio
.venv/bin/langgraph dev
```

### 필요한 환경변수 (.env)
```
UPSTAGE_API_KEY=
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
HF_TOKEN=
LANGSMITH_API_KEY=
LANGCHAIN_TRACING_V2=true
LANGCHAIN_PROJECT=benchmate
SUPABASE_URL=https://kuvtlhrrfjibjskmqlrg.supabase.co
SUPABASE_ANON_KEY=
```

---

*본 문서는 BenchMate 개발 세션 대화 내용을 압축한 요약본입니다.*
