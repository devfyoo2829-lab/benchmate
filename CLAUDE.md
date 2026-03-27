# BenchMate

Korean Enterprise LLM & Agent Evaluation Platform.
기업이 LLM 도입 시 Knowledge(지식)와 Agent(Tool calling) 두 축으로 정량 평가하는 자동화 벤치마크 에이전트.
Streamlit UI + LangGraph 파이프라인으로 구동된다.

## 기술 스택

- 파이프라인: LangGraph (StateGraph)
- 실험 추적: LangSmith
- Judge 모델: Qwen 2.5-32B (HuggingFace)
- UI: Streamlit (7 Screen)
- 언어: Python 3.11+

## 주요 명령어

- 실행: `streamlit run app.py`
- 테스트: `pytest tests/`
- 의존성 설치: `pip install -r requirements.txt`
- 타입 체크: `mypy pipeline/state.py`

## 폴더 구조

```
benchmate/
├── pipeline/
│   ├── state.py          # EvalState TypedDict (중앙 상태 — 모든 노드가 이것만 참조)
│   ├── graph.py          # LangGraph 그래프 조립
│   └── nodes/            # 노드 함수 10개 (각 파일 1개 노드)
├── data/
│   ├── questions/        # 도메인별 문항 JSON (QuestionItem 배열)
│   ├── tools/            # 도메인별 Tool 정의 JSON (mock_return 포함)
│   └── scenarios/        # 도메인별 Agent 시나리오 JSON
├── prompts/              # Judge 프롬프트 Jinja2 템플릿
├── ui/                   # Streamlit 화면 (screen1~7.py)
├── evaluators/           # tool_call_evaluator.py, score_aggregator.py
├── output/               # 평가 세션 결과 JSON (자동 저장)
└── tests/
```

## 핵심 설계 결정 (변경 금지)

1. **EvalState는 단일 진실 공급원**: 모든 노드는 EvalState만 참조. 노드 간 직접 데이터 전달 없음.
2. **call 채점은 코드, 나머지는 Judge**: `evaluate_call` 노드는 LLM 없이 JSON 파싱 후 코드로 비교.
3. **Position Bias 제거는 Knowledge에만 적용**: A→B, B→A 교차 채점 후 평균.
4. **Tool 실행은 Simulated(Mock)**: scenario JSON의 `turns[].content`에 사전 정의된 값 사용. 실제 API 호출 없음.
5. **Judge 출력은 항상 JSON**: 파싱 실패 시 최대 3회 재시도 → 초과 시 Human Review 큐 강제 등록.

## 노드 실행 순서

```
load_scenarios → route_mode
  → [Knowledge] generate_responses → judge_knowledge
  → [Agent]     generate_tool_calls → evaluate_call → judge_agent
  → validate_scores (재시도 분기) → flag_human_review
  → aggregate_results → generate_report → END
```

## 코딩 스타일

- Python 타입 힌트 필수 (TypedDict, List, Optional 등)
- 모든 노드 함수 시그니처: `def node_name(state: EvalState) -> dict:`
- 반환값은 변경된 필드만 포함하는 부분 딕셔너리
- 비동기 API 호출: asyncio + asyncio.gather로 병렬 처리
- Judge 프롬프트: Jinja2 템플릿 (`prompts/*.txt`) 렌더링
- 환경변수: `.env` 파일 사용, 코드에 API 키 직접 삽입 금지

## 참고 문서

- 상세 설계: `docs/` 폴더 참조 (기획서, 데이터구조설계, Agent설계, 데이터요구사항)
- EvalState 전체 구조: `pipeline/state.py`
- 노드별 입출력 명세: Agent 설계 문서
- 도메인 JSON 스키마: 데이터 구조 설계 문서