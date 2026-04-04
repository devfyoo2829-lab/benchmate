# BenchMate: Korean Enterprise LLM Evaluation Platform

*SeSAC AI 서비스 기획 최종 프로젝트 | 2026.03 | 작성자: 곽승연*

## Overview

BenchMate는 기업의 LLM 도입 의사결정을 지원하는 자동화 벤치마크 플랫폼입니다. 담당자가 자사 업무 질문과 정답을 입력하면, 복수의 LLM에게 동일한 문항을 던지고 **Knowledge(지식 응답 품질)**와 **Agent(Tool Calling 정확도)** 두 축으로 자동 채점합니다. 결과는 2축 포지셔닝 매트릭스와 PM이 바로 보고서에 활용할 수 있는 McKinsey 스타일 PDF 리포트로 출력됩니다.

기존 글로벌 벤치마크(MMLU 등)는 영어·범용 지식 중심이고, 단순 Q&A 체감 테스트는 정량화·재현이 불가합니다. BenchMate는 한국어 실무 도메인과 Tool Calling 시나리오를 결합해 "구매자 입장의 평가"를 가능하게 합니다.

## Core Capabilities

1. **Dual-Axis Evaluation**: Knowledge 5개 축(정확성·한국어 자연성·할루시네이션·도메인 전문성·응답 적절성)과 Agent 4개 항목(Tool 호출·슬롯 요청·거절 적절성·결과 전달)을 하나의 실행으로 동시 평가합니다.

2. **Instance-Specific Rubric**: BiGGen Bench(NAACL 2025 Best Paper) 방법론을 차용해 모든 문항에 동일한 기준을 적용하는 대신, 각 문항마다 고유한 핵심 채점 포인트를 Judge 프롬프트에 주입합니다.

3. **Position Bias Elimination**: Knowledge 채점에서 A→B, B→A 순서를 교차 적용한 뒤 평균을 산출해 Judge 모델의 순서 편향을 제거합니다.

4. **Hybrid Scoring Architecture**: Tool 호출 정확도는 JSON 파싱 기반 코드로, 나머지 품질 항목은 Qwen 2.5-32B Judge가 평가하는 이중 채점 구조로 LLM 판단 오류를 최소화합니다.

5. **Human-in-the-Loop Review**: Judge 파싱 실패·할루시네이션 감지·교차 편차 초과 항목을 자동으로 검토 큐에 등록하고, 담당자 수정 점수를 반영한 AI 채점 신뢰도를 실시간으로 산출합니다.

6. **PM Report Generation**: Positioning Matrix·레이더 차트·강점/리스크 분석을 포함한 경영진용 PDF와 GPT-4o 기반 해석 텍스트를 자동 생성해 도입 결정 보고 자료로 즉시 활용할 수 있습니다.

## Technical Architecture

파이프라인은 LangGraph StateGraph 위에서 동작하며 `EvalState` TypedDict 하나를 중앙 상태로 사용합니다.

- **단일 진실 공급원**: 모든 노드는 EvalState만 참조하며, 반환값은 변경된 필드만 담은 부분 딕셔너리입니다. 노드 간 직접 데이터 전달은 없습니다.
- **결정론적 Agent 채점**: Tool 호출 성공 여부는 LLM 판단 없이 파라미터 키·값을 코드로 직접 비교합니다. Judge는 구조화 판단이 필요 없는 품질 항목만 담당합니다.
- **Simulated Tool Execution**: 실제 외부 API 없이 시나리오 JSON의 Mock 반환값으로 Agent 평가를 수행해 재현 가능하고 비용 없는 테스트 환경을 구성합니다.
- **비동기 병렬 처리**: 모델 응답 수집과 Judge 호출은 `asyncio.gather`로 병렬 실행되어 복수 모델 평가 시 대기 시간을 최소화합니다.

Judge 모델로 Qwen 2.5-32B를 선택한 이유는 피평가 모델(Solar Pro, GPT-4o, Claude Sonnet, HyperCLOVA X, EXAONE)과의 이해충돌을 피하면서, 한국어(KMMLU) 공식 지원과 JSON 출력 안정성을 검증했기 때문입니다.

## Pipeline Flow

```
load_scenarios → route_mode
  → [Knowledge]  generate_responses → judge_knowledge
  → [Agent]      generate_tool_calls → evaluate_call → judge_agent
  → validate_scores → flag_human_review
  → aggregate_results → generate_report → END
```

Integrated 모드에서는 `_integrated_phase` 플래그를 통해 Knowledge 경로 완료 후 Agent 경로로 자동 전환됩니다. Judge JSON 파싱 실패 시 최대 3회 재시도하며, 초과 시 Human Review 큐에 강제 등록합니다.

## Supported Domains

| 도메인 | Tool 예시 |
|---|---|
| 금융 | `search_loan_rate`, `calculate_interest` |
| 법률·규정 | `search_regulation`, `check_compliance` |
| 인사·HR | `search_hr_policy`, `create_feedback_draft` |
| 고객응대·CS | `search_faq`, `create_response_draft` |
| 제조·기술문서 | `search_manual`, `get_defect_history` |

## Project Structure

```
benchmate/
├── pipeline/
│   ├── state.py          # EvalState TypedDict — 전체 파이프라인 중앙 상태
│   ├── graph.py          # LangGraph StateGraph 조립
│   └── nodes/            # 노드 함수 10개 (파일 1개 = 노드 1개)
├── data/
│   ├── questions/        # 도메인별 Knowledge 문항 JSON
│   ├── tools/            # 도메인별 Tool 정의 + Mock 반환값
│   └── scenarios/        # 도메인별 Agent 시나리오 JSON
├── prompts/              # Judge 프롬프트 Jinja2 템플릿
├── ui/                   # Streamlit 7-Screen 인터페이스
├── evaluators/           # Tool 호출 코드 기반 채점 로직
└── output/               # 평가 세션 결과 JSON (자동 저장)
```

## Getting Started

```bash
# 의존성 설치
pip install -r requirements.txt

# 환경변수 설정 (.env)
UPSTAGE_API_KEY=...
OPENAI_API_KEY=...
ANTHROPIC_API_KEY=...
HF_TOKEN=...
LANGSMITH_API_KEY=...

# 실행
streamlit run app.py
```

## Tech Stack

| 구성 요소 | 기술 |
|---|---|
| 파이프라인 | LangGraph (StateGraph) |
| Judge 모델 | Qwen 2.5-32B via HuggingFace Inference API |
| 실험 추적 | LangSmith |
| UI | Streamlit (7 Screen) |
| PDF 생성 | ReportLab |
| 언어 | Python 3.11+ |

## References

- BiGGen Bench — NAACL 2025 Best Paper, LG AI Research
- 올거나이즈 LLM 평가 플랫폼 — Tool Calling 4축 평가 방법론 (2025.02)
- Prometheus 2 — EMNLP 2024
- MT-Bench — NeurIPS 2023
