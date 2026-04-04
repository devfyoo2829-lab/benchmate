-- BenchMate Supabase PostgreSQL Schema
-- RLS 비활성화 (개발 단계)

-- 1. eval_sessions
CREATE TABLE IF NOT EXISTS eval_sessions (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id      TEXT        UNIQUE NOT NULL,
    eval_mode       TEXT        NOT NULL CHECK (eval_mode IN ('knowledge', 'agent', 'integrated')),
    domain          TEXT        NOT NULL,
    selected_models JSONB,
    judge_reliability FLOAT,
    estimated_cost  JSONB,
    summary_table   JSONB,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_eval_sessions_session_id ON eval_sessions(session_id);

ALTER TABLE eval_sessions DISABLE ROW LEVEL SECURITY;


-- 2. model_responses
CREATE TABLE IF NOT EXISTS model_responses (
    id               UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id       TEXT    NOT NULL REFERENCES eval_sessions(session_id) ON DELETE CASCADE,
    model_name       TEXT    NOT NULL,
    item_id          TEXT    NOT NULL,
    response_text    TEXT,
    tool_call_output JSONB,
    latency_ms       INTEGER,
    input_tokens     INTEGER,
    output_tokens    INTEGER,
    status           TEXT    CHECK (status IN ('success', 'failed')),
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_model_responses_session_id ON model_responses(session_id);

ALTER TABLE model_responses DISABLE ROW LEVEL SECURITY;


-- 3. knowledge_scores
CREATE TABLE IF NOT EXISTS knowledge_scores (
    id               UUID  PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id       TEXT  NOT NULL REFERENCES eval_sessions(session_id) ON DELETE CASCADE,
    model_name       TEXT  NOT NULL,
    question_id      TEXT  NOT NULL,
    accuracy         FLOAT,
    fluency          FLOAT,
    hallucination    FLOAT,
    domain_expertise FLOAT,
    utility          FLOAT,
    total            FLOAT,
    judge_order      TEXT  CHECK (judge_order IN ('ab', 'ba', 'final')),
    reason           TEXT,
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_knowledge_scores_session_id ON knowledge_scores(session_id);

ALTER TABLE knowledge_scores DISABLE ROW LEVEL SECURITY;


-- 4. agent_scores
CREATE TABLE IF NOT EXISTS agent_scores (
    id               UUID  PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id       TEXT  NOT NULL REFERENCES eval_sessions(session_id) ON DELETE CASCADE,
    model_name       TEXT  NOT NULL,
    scenario_id      TEXT  NOT NULL,
    call_score       FLOAT,
    slot_score       FLOAT,
    relevance_score  FLOAT,
    completion_score FLOAT,
    reason           TEXT,
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agent_scores_session_id ON agent_scores(session_id);

ALTER TABLE agent_scores DISABLE ROW LEVEL SECURITY;


-- 5. human_reviews
CREATE TABLE IF NOT EXISTS human_reviews (
    id            UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id    TEXT    NOT NULL REFERENCES eval_sessions(session_id) ON DELETE CASCADE,
    item_id       TEXT    NOT NULL,
    item_type     TEXT    NOT NULL CHECK (item_type IN ('knowledge', 'agent')),
    model_name    TEXT    NOT NULL,
    judge_score   JSONB,
    human_score   JSONB,
    review_reason TEXT,
    is_reviewed   BOOLEAN DEFAULT FALSE,
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_human_reviews_session_id ON human_reviews(session_id);

ALTER TABLE human_reviews DISABLE ROW LEVEL SECURITY;


-- 6. eval_reports
CREATE TABLE IF NOT EXISTS eval_reports (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id     TEXT NOT NULL REFERENCES eval_sessions(session_id) ON DELETE CASCADE,
    pm_report_text TEXT,
    best_model     TEXT,
    created_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_eval_reports_session_id ON eval_reports(session_id);

ALTER TABLE eval_reports DISABLE ROW LEVEL SECURITY;
