-- Fact Knowledge Layer — Production-Grade Financial Evidence Schema
CREATE EXTENSION IF NOT EXISTS vector;

-- ── Documents ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS documents (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    filename        text NOT NULL,
    sha256          text UNIQUE NOT NULL,
    r2_key          text NOT NULL,
    file_size_bytes bigint,
    page_count      int,
    status          text NOT NULL DEFAULT 'uploaded',
    created_at      timestamptz NOT NULL DEFAULT now()
);

-- ── Document Pages (100% of pages recorded, never dropped) ──────────
CREATE TABLE IF NOT EXISTS document_pages (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page_number int NOT NULL,
    width       real,
    height      real,
    png_key     text,
    route       text NOT NULL DEFAULT 'text',  -- 'text', 'scan', 'mixed', 'empty', 'error'
    char_count  int DEFAULT 0,
    table_count int DEFAULT 0,
    created_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (document_id, page_number)
);

-- Compatibility view for existing code expecting 'pages'
CREATE OR REPLACE VIEW pages AS
SELECT id, document_id, page_number AS page, width, height, png_key, route, created_at
FROM document_pages;

-- ── Document Sections & Heading Hierarchy ───────────────────────────
CREATE TABLE IF NOT EXISTS document_sections (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id   uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page_number   int NOT NULL,
    title         text NOT NULL,
    level         int NOT NULL DEFAULT 1,
    section_type  text NOT NULL DEFAULT 'narrative',  -- 'heading', 'financial_statements', 'notes', 'mda', 'audit_report'
    reading_order int NOT NULL DEFAULT 0,
    created_at    timestamptz NOT NULL DEFAULT now()
);

-- ── First-Class Financial Tables ────────────────────────────────────
CREATE TABLE IF NOT EXISTS document_tables (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id   uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page_number   int NOT NULL,
    table_index   int NOT NULL DEFAULT 0,
    bbox          jsonb,
    title         text,
    headers       jsonb NOT NULL DEFAULT '[]'::jsonb,
    grid          jsonb NOT NULL DEFAULT '[]'::jsonb,
    markdown_repr text NOT NULL,
    unit_hint     text,
    currency_hint text,
    period_hint   text,
    created_at    timestamptz NOT NULL DEFAULT now()
);

-- ── Document Chunks (Narrative, Tables, Footnotes) ───────────────────
CREATE TABLE IF NOT EXISTS document_chunks (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id   uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page_number   int NOT NULL,
    section_id    uuid REFERENCES document_sections(id) ON DELETE SET NULL,
    table_id      uuid REFERENCES document_tables(id) ON DELETE SET NULL,
    chunk_type    text NOT NULL DEFAULT 'paragraph',  -- 'paragraph', 'table', 'footnote', 'heading', 'needs_review'
    text          text NOT NULL,
    bbox          jsonb,
    reading_order int NOT NULL DEFAULT 0,
    heading       text,
    ocr_provider  text,
    created_at    timestamptz NOT NULL DEFAULT now()
);

-- Compatibility view for existing code expecting 'chunks'
CREATE OR REPLACE VIEW chunks AS
SELECT id, document_id, page_number AS page, chunk_type, text, bbox, heading, ocr_provider, created_at
FROM document_chunks;

-- ── Financial Entities / Companies ──────────────────────────────────
CREATE TABLE IF NOT EXISTS entities (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    canonical_name  text UNIQUE NOT NULL,
    legal_name      text,
    aliases         jsonb NOT NULL DEFAULT '[]'::jsonb,
    first_seen_at   timestamptz NOT NULL DEFAULT now()
);

-- Legacy alias mapping table for fast direct lookups
CREATE TABLE IF NOT EXISTS entity_aliases (
    alias     text PRIMARY KEY,
    canonical text NOT NULL
);

-- ── Financial Periods ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS financial_periods (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    canonical_period text UNIQUE NOT NULL,  -- 'FY2024', '2024-Q3', '2023', 'unspecified'
    period_type      text NOT NULL DEFAULT 'annual',  -- 'annual', 'quarterly', 'monthly', 'point_in_time', 'unspecified'
    year             int,
    quarter          int,
    start_date       date,
    end_date         date
);

-- ── Financial Metrics Taxonomy ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS financial_metrics (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    canonical_name text UNIQUE NOT NULL,
    category       text NOT NULL DEFAULT 'financial',  -- 'income_statement', 'balance_sheet', 'cash_flow', 'operational', 'governance'
    standard_unit  text,
    embedding      vector(768),
    first_seen_at  timestamptz NOT NULL DEFAULT now()
);

-- Legacy attribute namespace table compatibility
CREATE TABLE IF NOT EXISTS attribute_namespace (
    canonical     text PRIMARY KEY,
    embedding     vector(768),
    first_seen_at timestamptz NOT NULL DEFAULT now()
);

-- ── Extracted Facts ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS facts (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id       uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page_number       int,
    chunk_id          uuid REFERENCES document_chunks(id) ON DELETE SET NULL,
    table_id          uuid REFERENCES document_tables(id) ON DELETE SET NULL,
    entity_id         uuid REFERENCES entities(id) ON DELETE SET NULL,
    metric_id         uuid REFERENCES financial_metrics(id) ON DELETE SET NULL,
    period_id         uuid REFERENCES financial_periods(id) ON DELETE SET NULL,
    entity            text,
    attribute         text,
    entity_canon      text,
    attribute_canon   text,
    raw_value         text NOT NULL,
    norm_value        numeric,
    norm_unit         text,
    currency          text,
    period            text,
    scope             text,
    quote             text NOT NULL,
    confidence        real NOT NULL DEFAULT 1.0,
    validation_status text NOT NULL DEFAULT 'valid',  -- 'valid', 'flagged', 'low_confidence', 'suspicious'
    model             text,
    prompt_ver        text,
    prompt_hash       text,
    embedding         vector(768),
    created_at        timestamptz NOT NULL DEFAULT now()
);

-- ── Immutable Deduplicated Evidence Snippets ────────────────────────
CREATE TABLE IF NOT EXISTS evidence (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id   uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page          int,
    evidence_type text NOT NULL,  -- 'table_cell', 'table_row', 'paragraph', 'heading', 'ocr_text', 'calculation'
    content_hash  text UNIQUE NOT NULL,  -- SHA-256(content + page + evidence_type)
    content       text NOT NULL,
    bbox          jsonb,
    table_ref     jsonb,  -- {table_index, row, col, header}
    model_id      text,
    prompt_hash   text,
    created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS fact_evidence (
    fact_id     uuid NOT NULL REFERENCES facts(id) ON DELETE CASCADE,
    evidence_id uuid NOT NULL REFERENCES evidence(id) ON DELETE CASCADE,
    role        text NOT NULL DEFAULT 'source',  -- 'source', 'supporting', 'calculation_input', 'verification'
    PRIMARY KEY (fact_id, evidence_id)
);

-- ── Cross-Document & Intra-Document Relations ───────────────────────
CREATE TABLE IF NOT EXISTS fact_relations (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    fact_a        uuid NOT NULL REFERENCES facts(id) ON DELETE CASCADE,
    fact_b        uuid NOT NULL REFERENCES facts(id) ON DELETE CASCADE,
    relation      text NOT NULL,  -- 'corroborates', 'contradicts', 'contextual_variance', 'needs_review'
    explanation   text,
    rules_applied jsonb NOT NULL DEFAULT '[]'::jsonb,
    confidence    real,
    created_at    timestamptz NOT NULL DEFAULT now()
);

-- ── Deterministic Calculations ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS calculations (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    fact_id       uuid REFERENCES facts(id) ON DELETE SET NULL,
    formula       text NOT NULL,
    input_facts   jsonb NOT NULL,  -- [{fact_id, label, value}]
    result        numeric,
    result_unit   text,
    is_verified   boolean DEFAULT false,
    error         text,
    created_at    timestamptz NOT NULL DEFAULT now()
);

-- ── Durable Transactional Job Queue ─────────────────────────────────
CREATE TABLE IF NOT EXISTS jobs (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id     uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    stage           text NOT NULL DEFAULT 'queued',
    status          text NOT NULL DEFAULT 'pending',  -- 'pending', 'running', 'done', 'failed'
    progress        real NOT NULL DEFAULT 0.0,
    attempts        int NOT NULL DEFAULT 0,
    max_attempts    int NOT NULL DEFAULT 3,
    heartbeat_at    timestamptz,
    checkpoint_data jsonb,
    error           text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

-- ── Human Review Queue ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS review_queue (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    fact_id     uuid REFERENCES facts(id) ON DELETE CASCADE,
    relation_id uuid REFERENCES fact_relations(id) ON DELETE CASCADE,
    reason      text NOT NULL,  -- 'low_confidence', 'contradiction', 'anomaly:benford', 'anomaly:zscore', etc.
    status      text NOT NULL DEFAULT 'pending',  -- 'pending', 'approved', 'rejected', 'deferred'
    reviewer    text,
    decision    text,
    reviewed_at timestamptz,
    created_at  timestamptz NOT NULL DEFAULT now()
);

-- ── Analysis Findings ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS findings (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id       uuid,                          -- group related findings
    category      text NOT NULL,                  -- 'contradiction', 'anomaly', 'missing_disclosure', 'computational_error', 'contextual_variance', 'corroboration'
    severity      text NOT NULL DEFAULT 'medium', -- 'critical', 'high', 'medium', 'low', 'info'
    title         text NOT NULL,
    description   text NOT NULL,
    explanation   text,                           -- AI-generated contextual narrative
    fact_ids      uuid[] NOT NULL DEFAULT '{}',
    relation_ids  uuid[] NOT NULL DEFAULT '{}',
    evidence_ids  uuid[] NOT NULL DEFAULT '{}',
    document_ids  uuid[] NOT NULL DEFAULT '{}',
    details       jsonb NOT NULL DEFAULT '{}',    -- computation details, thresholds, deltas
    status        text NOT NULL DEFAULT 'open',   -- 'open', 'confirmed', 'dismissed', 'resolved'
    created_at    timestamptz NOT NULL DEFAULT now()
);

-- ── System Audit Trail ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS audit (
    id     bigserial PRIMARY KEY,
    at     timestamptz NOT NULL DEFAULT now(),
    actor  text,
    action text NOT NULL,
    target jsonb,
    meta   jsonb
);

-- ── Indexes ─────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_facts_embedding ON facts USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_facts_entity_attr ON facts (entity_canon, attribute_canon);
CREATE INDEX IF NOT EXISTS idx_facts_document_id ON facts (document_id);
CREATE INDEX IF NOT EXISTS idx_facts_validation ON facts (validation_status);

CREATE INDEX IF NOT EXISTS idx_metrics_embedding ON financial_metrics USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_attribute_ns_embedding ON attribute_namespace USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS idx_doc_pages_doc_num ON document_pages (document_id, page_number);
CREATE INDEX IF NOT EXISTS idx_doc_sections_doc ON document_sections (document_id, page_number);
CREATE INDEX IF NOT EXISTS idx_doc_tables_doc ON document_tables (document_id, page_number);
CREATE INDEX IF NOT EXISTS idx_doc_chunks_doc ON document_chunks (document_id, page_number);

CREATE INDEX IF NOT EXISTS idx_evidence_hash ON evidence (content_hash);
CREATE INDEX IF NOT EXISTS idx_evidence_doc_page ON evidence (document_id, page);

CREATE INDEX IF NOT EXISTS idx_fact_evidence_fact ON fact_evidence (fact_id);
CREATE INDEX IF NOT EXISTS idx_fact_evidence_evidence ON fact_evidence (evidence_id);

CREATE INDEX IF NOT EXISTS idx_relations_ab ON fact_relations (fact_a, fact_b);
CREATE INDEX IF NOT EXISTS idx_relations_type ON fact_relations (relation);

CREATE INDEX IF NOT EXISTS idx_jobs_status_created ON jobs (status, created_at);
CREATE INDEX IF NOT EXISTS idx_jobs_heartbeat ON jobs (heartbeat_at) WHERE status = 'running';

CREATE INDEX IF NOT EXISTS idx_review_status_created ON review_queue (status, created_at);

CREATE INDEX IF NOT EXISTS idx_findings_category ON findings (category);
CREATE INDEX IF NOT EXISTS idx_findings_severity ON findings (severity);
CREATE INDEX IF NOT EXISTS idx_findings_status ON findings (status);
CREATE INDEX IF NOT EXISTS idx_findings_case ON findings (case_id) WHERE case_id IS NOT NULL;
