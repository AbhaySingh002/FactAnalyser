CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE documents (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    filename    text NOT NULL,
    sha256      text UNIQUE NOT NULL,
    r2_key      text NOT NULL,
    page_count  int,
    status      text NOT NULL DEFAULT 'uploaded',
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE pages (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id uuid NOT NULL REFERENCES documents(id),
    page        int NOT NULL,
    width       real,
    height      real,
    png_key     text,
    route       text,
    created_at  timestamptz NOT NULL DEFAULT now()
);


CREATE TABLE chunks (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id  uuid NOT NULL REFERENCES documents(id),
    page         int NOT NULL,
    chunk_type   text,
    text         text,
    bbox         jsonb,
    heading      text,
    ocr_provider text,
    created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE facts (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    chunk_id        uuid REFERENCES chunks(id),
    document_id     uuid NOT NULL REFERENCES documents(id),
    entity          text,
    attribute       text,
    entity_canon    text,
    attribute_canon text,
    raw_value       text,
    norm_value      numeric,
    norm_unit       text,
    currency        text,
    period          text,
    scope           text,
    quote           text,
    confidence      real,
    model           text,
    prompt_ver      text,
    embedding       vector(768),
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE fact_relations (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    fact_a        uuid NOT NULL REFERENCES facts(id),
    fact_b        uuid NOT NULL REFERENCES facts(id),
    relation      text NOT NULL,
    explanation   text,
    rules_applied jsonb,
    confidence    real,
    created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE attribute_namespace (
    canonical     text PRIMARY KEY,
    embedding     vector(768),
    first_seen_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE entity_aliases (
    alias     text PRIMARY KEY,
    canonical text NOT NULL
);

CREATE TABLE jobs (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id uuid NOT NULL REFERENCES documents(id),
    stage       text NOT NULL,
    status      text NOT NULL,
    error       text,
    updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE audit (
    id     bigserial PRIMARY KEY,
    at     timestamptz NOT NULL DEFAULT now(),
    actor  text,
    action text NOT NULL,
    target jsonb,
    meta   jsonb
);

-- Indexes
CREATE INDEX ON facts USING hnsw (embedding vector_cosine_ops);
CREATE INDEX ON attribute_namespace USING hnsw (embedding vector_cosine_ops);
CREATE INDEX ON facts (entity_canon, attribute_canon);
CREATE INDEX ON chunks (document_id, page);
CREATE INDEX ON pages (document_id, page);
