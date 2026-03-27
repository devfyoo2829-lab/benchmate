"""
BenchMate — EvalState 중앙 상태 정의
모든 LangGraph 노드는 이 파일의 TypedDict만 참조한다.
설계 기준: docs/BenchMate_데이터구조설계.md v1.1
"""

from typing import Dict, List, Literal, Optional, TypedDict


# ── 하위 타입 정의 ──────────────────────────────────────────────────────────────


class QuestionItem(TypedDict):
    """Knowledge 평가용 단일 문항."""

    id: str                    # 문항 고유 ID. 예: "fin_001"
    domain: str                # 도메인. "finance" | "legal" | "hr" | "cs" | "manufacturing"
    question: str              # 평가 질문 텍스트 (10자 이상)
    reference_answer: str      # 담당자가 등록한 정답. Judge의 채점 기준점
    instance_rubric: str       # 이 문항에서 특히 봐야 할 채점 포인트. Judge 프롬프트에 주입됨
    difficulty: str            # 난이도. "easy" | "medium" | "hard"
    task_type: str             # 질문 유형. "explanation" | "calculation" | "summary" | "translation" | "comparison"


class ToolDefinition(TypedDict):
    """Agent 평가에서 사용할 단일 Tool 정의."""

    name: str                  # Tool 이름. 예: "search_loan_rate"
    description: str           # Tool 기능 설명. LLM에게 주입됨
    parameters: List[Dict]     # 파라미터 목록. 각 원소: {name, type, required, description}
    mock_return: Dict          # Simulated 반환값. 실제 API 호출 대신 사용되는 사전 정의 결과


class ContextDependency(TypedDict):
    """Multi-turn 시나리오에서 이전 턴의 값이 이후 턴에서 사용되는 의존 관계."""

    from_turn: int             # 값이 생성된 턴 인덱스 (tool_result 턴)
    to_turn: int               # 해당 값을 사용해야 하는 턴 인덱스 (user 입력 턴)
    carried_value: str         # 전달되어야 할 파라미터 키 이름. 예: "annual_rate"
    description: str           # 의존 관계 설명. 예: "Turn 1의 final_rate 4.7을 Turn 2의 annual_rate로 사용해야 함"


class ScenarioItem(TypedDict):
    """Agent 평가용 단일 시나리오. Single-turn 및 Multi-turn 모두 포함."""

    id: str                                          # 시나리오 고유 ID. 예: "fin_sc_001"
    domain: str                                      # 도메인
    scenario_type: str                               # "single_A" | "single_B" | "single_C" | "multi"
                                                     #   single_A: 정상 호출
                                                     #   single_B: 정보 부족 → 슬롯 요청
                                                     #   single_C: 불가능한 요청 → 거절
                                                     #   multi: 다중 턴 연속 호출
    turns: List[Dict]                                # 턴별 대화 정의. 각 원소: {turn_index, role, content}
    expected_tool_calls: List[Dict]                  # 정답 Tool 호출 목록. 각 원소: {turn_index, tool_name, parameters}
    context_dependency: List[ContextDependency]      # Multi-turn 맥락 의존 관계. single_* 시나리오는 빈 리스트
    available_tools: List[str]                       # 이 시나리오에서 사용 가능한 Tool 이름 목록


class ModelResponse(TypedDict):
    """단일 모델의 단일 문항/시나리오에 대한 응답 수집 결과."""

    model_name: str                  # 응답한 모델 이름. 예: "solar-pro"
    item_id: str                     # question_id 또는 scenario_id. Knowledge/Agent 모드 통일 식별자
    response_text: str               # 모델의 자연어 응답 (Knowledge 모드 및 Agent completion 응답)
    tool_call_output: Optional[Dict] # 모델의 Tool 호출 결과 — JSON 파싱 성공 시 채워짐 (Agent 모드)
    raw_output: Optional[str]        # Tool 호출 원본 문자열 — 파싱 전 보존. 디버깅 및 재시도용 (Agent 모드)
    latency_ms: int                  # API 응답 지연 시간 (밀리초)
    input_tokens: int                # 입력 토큰 수
    output_tokens: int               # 출력 토큰 수
    status: str                      # 호출 상태. "success" | "retry" | "failed"


class KnowledgeScore(TypedDict):
    """Knowledge Judge가 산출한 단일 문항 × 단일 모델의 채점 결과."""

    question_id: str           # 채점 대상 문항 ID
    model_name: str            # 채점 대상 모델 이름
    accuracy: int              # 정확성 (1~5). 사실 오류 없이 정확한 정보를 제공하는가
    fluency: int               # 한국어 자연성 (1~5). 자연스러운 한국어 표현과 문법인가
    hallucination: int         # 할루시네이션 부재 (1~5). 5=전혀 없음. 없는 정보를 만들어내지 않는가
    domain_expertise: int      # 도메인 전문성 (1~5). 해당 도메인 용어를 정확히 사용하는가
    utility: int               # 응답 적절성 (1~5). 질문 의도에 맞는 답변 형식과 길이인가
    total: int                 # 5개 항목 합계 (5~25)
    reason: str                # Judge의 채점 이유 (2~3문장)
    judge_order: str           # Position Bias 교차 평가 순서. "ab" | "ba"


class AgentScore(TypedDict):
    """evaluate_call 노드(코드 채점) 및 judge_agent 노드(LLM 채점)의 결합 결과."""

    scenario_id: str                       # 채점 대상 시나리오 ID
    turn_index: int                        # 해당 채점이 이루어진 턴 인덱스
    model_name: str                        # 채점 대상 모델 이름
    tool_name_extracted: Optional[str]     # evaluate_call이 파싱한 Tool 이름. JSON 파싱 실패 시 None
    params_extracted: Optional[Dict]       # evaluate_call이 파싱한 파라미터 dict. JSON 파싱 실패 시 None
    call_correct: bool                     # Tool 이름이 정답과 일치하는지 여부 (코드 기반)
    params_match: bool                     # 파라미터가 정답과 완전 일치하는지 여부 (코드 기반)
    missing_params: List[str]              # 정답에는 있으나 모델이 누락한 파라미터 키 목록
    extra_params: List[str]                # 정답에는 없으나 모델이 추가로 넣은 파라미터 키 목록
    call_score: int                        # Tool 호출 정확도 점수. 0 또는 1 (코드 기반 채점)
    slot_score: Optional[int]              # 슬롯 요청 적절성 점수. 0 또는 1 (Judge). single_A / multi 에서는 None
    relevance_score: Optional[int]         # 거절 적절성 점수. 0 또는 1 (Judge). single_A / single_B / multi 에서는 None
    completion_score: Optional[int]        # 결과 전달 품질 점수. 1~3 (Judge). 자연어 응답이 있는 턴에만 적용
    reason: str                            # 채점 이유 요약


class HumanScoreDetail(TypedDict):
    """Human Review 단계에서 담당자가 직접 수정 입력하는 점수 상세."""

    # Knowledge 수정 점수 (knowledge 또는 integrated 모드에서 사용)
    accuracy: Optional[int]          # 정확성 수정 점수 (1~5). 수정 없으면 None
    fluency: Optional[int]           # 한국어 자연성 수정 점수 (1~5). 수정 없으면 None
    hallucination: Optional[int]     # 할루시네이션 부재 수정 점수 (1~5). 수정 없으면 None
    domain_expertise: Optional[int]  # 도메인 전문성 수정 점수 (1~5). 수정 없으면 None
    utility: Optional[int]           # 응답 적절성 수정 점수 (1~5). 수정 없으면 None

    # Agent 수정 점수 (agent 또는 integrated 모드에서 사용)
    call_score: Optional[int]        # Tool 호출 정확도 수정 점수. 0 또는 1. 수정 없으면 None


class HumanReviewItem(TypedDict):
    """Human Review 큐의 단일 검토 항목."""

    item_id: str                              # 검토 대상 question_id 또는 scenario_id
    item_type: str                            # 항목 유형. "knowledge" | "agent"
    model_name: str                           # 검토 대상 모델 이름
    judge_score: Dict                         # Judge가 산출한 원본 점수 (KnowledgeScore 또는 AgentScore dict)
    human_score: Optional[HumanScoreDetail]   # 담당자가 수정 입력한 점수. 검토 전: None
    review_reason: str                        # 큐 등록 사유. 예: "편차 큰 항목" | "hallucination 낮음" | "call 실패" | "랜덤 샘플링"
    is_reviewed: bool                         # 담당자 검토 완료 여부


# ── 메인 EvalState ──────────────────────────────────────────────────────────────


class EvalState(TypedDict):
    """
    LangGraph 파이프라인 전체에서 공유되는 중앙 상태 객체.
    모든 노드는 EvalState를 유일한 입력/출력으로 사용하며,
    반환값은 변경된 필드만 포함하는 부분 딕셔너리(partial dict)여야 한다.
    """

    # ── 1. 평가 설정 (Screen 1~3에서 사용자가 입력) ─────────────────────────────
    eval_mode: str             # 평가 모드. "knowledge" | "agent" | "integrated"
    domain: str                # 평가 도메인. "finance" | "legal" | "hr" | "cs" | "manufacturing"
    selected_models: List[str] # 비교 대상 모델 이름 목록. 예: ["solar-pro", "gpt-4o", "claude-sonnet"]

    # ── 2. 문항 및 시나리오 (load_scenarios 노드가 채움) ────────────────────────
    questions: List[QuestionItem]          # Knowledge 평가 문항 목록 (knowledge / integrated 모드)
    scenarios: List[ScenarioItem]          # Agent 평가 시나리오 목록 (agent / integrated 모드)
    available_tools: List[ToolDefinition]  # 이번 평가에서 사용할 Tool 정의 목록
    rubric_text: str                       # 도메인 기본 루브릭 텍스트. Judge 프롬프트에 공통 주입됨

    # ── 3. 응답 수집 (generate_responses / generate_tool_calls 노드가 채움) ──────
    model_responses: List[ModelResponse]   # 전체 모델 응답 누적 목록

    # ── 4. 채점 결과 ──────────────────────────────────────────────────────────────
    knowledge_scores_ab: List[KnowledgeScore]    # A→B 순서로 채점한 Knowledge 점수 목록
    knowledge_scores_ba: List[KnowledgeScore]    # B→A 순서로 채점한 Knowledge 점수 목록 (Position Bias 제거용)
    knowledge_scores_final: List[KnowledgeScore] # ab / ba 평균으로 산출한 최종 Knowledge 점수 목록
    agent_scores: List[AgentScore]               # Agent 채점 결과 누적 목록 (코드 채점 + Judge 채점 포함)
    retry_count: int                             # Judge JSON 파싱 실패 시 재시도 카운터. 최대 3회 초과 시 human_review_queue 강제 등록
    last_failed_branch: Optional[str]            # 파싱 실패가 발생한 브랜치. "knowledge" | "agent" | None
    _retry_targets: List                         # 재시도 대상 항목 목록 (_parse_failed=True인 score 객체들)

    # ── 5. Human Review ───────────────────────────────────────────────────────────
    human_review_queue: List[HumanReviewItem]    # 담당자 검토 큐. flag_human_review 노드가 항목을 추가함
    judge_reliability: Optional[float]           # Judge-Human 일치율 (%). 검토 전: None

    # ── 6. 집계 및 출력 (aggregate_results / generate_report 노드가 채움) ─────────
    summary_table: Optional[Dict]      # 모델 × 도메인 × 기준 집계 테이블. {model: {domain: {criterion: score}}}
    estimated_cost: Optional[Dict]     # 모델별 추정 API 비용. {model_name: cost_usd}
    pm_report_text: Optional[str]      # PM 해석 리포트 마크다운 문자열
    eval_session_id: str               # 세션 고유 ID. 타임스탬프 기반. 예: "eval_20260315_143022"
