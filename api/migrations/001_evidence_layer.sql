-- Migration: Evidence-First Financial Intelligence Engine (Phase 1)
-- Additive only — no existing data affected

-- ── Evidence Provenance ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS evidence (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id   uuid NOT NULL REFERENCES documents(id),
    page          int,
    evidence_type text NOT NULL,  -- 'table_cell', 'paragraph', 'ocr_text', 'calculation', 'external'
    content_hash  text NOT NULL,  -- SHA-256 of (content + page + evidence_type) for tamper detection
    content       text NOT NULL,
    bbox          jsonb,
    table_ref     jsonb,          -- {table_index, row, col, header}
    model_id      text,
    prompt_hash   text,
    created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS fact_evidence (
    fact_id     uuid NOT NULL REFERENCES facts(id),
    evidence_id uuid NOT NULL REFERENCES evidence(id),
    role        text NOT NULL DEFAULT 'source',  -- 'source', 'calculation_input', 'verification'
    PRIMARY KEY (fact_id, evidence_id)
);

-- ── Deterministic Calculations ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS calculations (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    fact_id       uuid REFERENCES facts(id),
    formula       text NOT NULL,
    input_facts   jsonb NOT NULL,  -- [{fact_id, label, value}]
    result        numeric,
    result_unit   text,
    is_verified   boolean DEFAULT false,
    error         text,
    created_at    timestamptz NOT NULL DEFAULT now()
);

-- ── Human Review Queue ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS review_queue (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    fact_id     uuid REFERENCES facts(id),
    relation_id uuid REFERENCES fact_relations(id),
    reason      text NOT NULL,       -- 'low_confidence', 'contradiction', 'anomaly', 'calculation_mismatch'
    status      text NOT NULL DEFAULT 'pending',  -- 'pending', 'approved', 'rejected', 'deferred'
    reviewer    text,
    decision    text,
    reviewed_at timestamptz,
    created_at  timestamptz NOT NULL DEFAULT now()
);

-- ── Additive columns on existing tables ─────────────────────────────
ALTER TABLE facts ADD COLUMN IF NOT EXISTS prompt_hash text;

-- ── Indexes ─────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_evidence_doc_page ON evidence (document_id, page);
CREATE INDEX IF NOT EXISTS idx_evidence_hash ON evidence (content_hash);
CREATE INDEX IF NOT EXISTS idx_review_status ON review_queue (status, created_at);
CREATE INDEX IF NOT EXISTS idx_calculations_fact ON calculations (fact_id);
CREATE INDEX IF NOT EXISTS idx_fact_evidence_fact ON fact_evidence (fact_id);
CREATE INDEX IF NOT EXISTS idx_fact_evidence_evidence ON fact_evidence (evidence_id);
