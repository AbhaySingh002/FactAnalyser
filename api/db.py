"""Database helpers — psycopg3 pool, PostgreSQL transactional queue, financial evidence graph.

DESIGN NOTES:
- Lazy connection pool initialization to prevent module import crashes when DB is connecting.
- Transactional job queue with FOR UPDATE SKIP LOCKED, stage checkpointing, and heartbeat recovery.
- Normalized financial graph: documents, pages, sections, tables, entities, periods, metrics, facts.
- Deduplicated evidence provenance via SHA-256 content hashes.
- Auditing enabled from day one.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv
load_dotenv()

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://localhost:5432/factlayer")

# Lazy pool initialization (open=False) to avoid import crashes when PostgreSQL is not immediately active
pool = ConnectionPool(
    DATABASE_URL,
    min_size=1,
    max_size=10,
    kwargs={"row_factory": dict_row},
    open=False,
)


def _ensure_pool():
    if not getattr(pool, "_opened", False):
        try:
            pool.open()
        except Exception:
            pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def q(sql: str, params: tuple | list | None = None) -> list[dict]:
    """Execute raw SQL query with parameters using the connection pool."""
    _ensure_pool()
    with pool.connection() as conn:
        return conn.execute(sql, params or ()).fetchall()


# ── documents ────────────────────────────────────────────────────────

def new_document(filename: str, sha256: str, r2_key: str, file_size_bytes: int | None = None) -> dict:
    _ensure_pool()
    with pool.connection() as conn:
        row = conn.execute(
            """INSERT INTO documents (filename, sha256, r2_key, file_size_bytes)
               VALUES (%s, %s, %s, %s)
               RETURNING *""",
            (filename, sha256, r2_key, file_size_bytes),
        ).fetchone()
        return dict(row)


insert_document = new_document


def get_document(document_id: str) -> dict | None:
    _ensure_pool()
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT * FROM documents WHERE id = %s", (str(document_id),)
        ).fetchone()
        return dict(row) if row else None


def get_document_by_sha(sha256: str) -> dict | None:
    _ensure_pool()
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT * FROM documents WHERE sha256 = %s", (sha256,)
        ).fetchone()
        return dict(row) if row else None


def list_documents() -> list[dict]:
    _ensure_pool()
    with pool.connection() as conn:
        rows = conn.execute(
            """SELECT d.*,
                      (SELECT COUNT(*) FROM document_pages p WHERE p.document_id = d.id) AS page_count_actual,
                      (SELECT COUNT(*) FROM document_tables t WHERE t.document_id = d.id) AS table_count,
                      (SELECT COUNT(*) FROM facts f WHERE f.document_id = d.id) AS fact_count
               FROM documents d
               ORDER BY d.created_at DESC"""
        ).fetchall()
        return [dict(r) for r in rows]


def update_document_page_count(document_id: str, page_count: int):
    _ensure_pool()
    with pool.connection() as conn:
        conn.execute(
            "UPDATE documents SET page_count = %s WHERE id = %s",
            (page_count, str(document_id)),
        )


def update_document_status(document_id: str, status: str):
    _ensure_pool()
    with pool.connection() as conn:
        conn.execute(
            "UPDATE documents SET status = %s WHERE id = %s",
            (status, str(document_id)),
        )


# ── document_pages ───────────────────────────────────────────────────

def insert_page(
    document_id: str,
    page: int,
    width: float | None,
    height: float | None,
    png_key: str | None,
    route: str = "text",
    char_count: int = 0,
    table_count: int = 0,
) -> dict:
    """Insert or update page record (100% of pages recorded, never dropped)."""
    _ensure_pool()
    with pool.connection() as conn:
        row = conn.execute(
            """INSERT INTO document_pages (document_id, page_number, width, height, png_key, route, char_count, table_count)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (document_id, page_number) DO UPDATE
               SET width = EXCLUDED.width,
                   height = EXCLUDED.height,
                   png_key = EXCLUDED.png_key,
                   route = EXCLUDED.route,
                   char_count = EXCLUDED.char_count,
                   table_count = EXCLUDED.table_count
               RETURNING *""",
            (str(document_id), page, width, height, png_key, route, char_count, table_count),
        ).fetchone()
        return dict(row)


def get_page(document_id: str, page: int) -> dict | None:
    _ensure_pool()
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT * FROM document_pages WHERE document_id = %s AND page_number = %s",
            (str(document_id), page),
        ).fetchone()
        return dict(row) if row else None


def list_pages_for_document(document_id: str) -> list[dict]:
    _ensure_pool()
    with pool.connection() as conn:
        rows = conn.execute(
            "SELECT * FROM document_pages WHERE document_id = %s ORDER BY page_number ASC",
            (str(document_id),),
        ).fetchall()
        return [dict(r) for r in rows]


def update_page_route(document_id: str, page: int, route: str):
    _ensure_pool()
    with pool.connection() as conn:
        conn.execute(
            "UPDATE document_pages SET route = %s WHERE document_id = %s AND page_number = %s",
            (route, str(document_id), page),
        )


# ── document_sections & tables ───────────────────────────────────────

def insert_section(
    document_id: str,
    page_number: int,
    title: str,
    level: int = 1,
    section_type: str = "narrative",
    reading_order: int = 0,
) -> dict:
    _ensure_pool()
    with pool.connection() as conn:
        row = conn.execute(
            """INSERT INTO document_sections (document_id, page_number, title, level, section_type, reading_order)
               VALUES (%s, %s, %s, %s, %s, %s)
               RETURNING *""",
            (str(document_id), page_number, title, level, section_type, reading_order),
        ).fetchone()
        return dict(row)


def insert_table(
    document_id: str,
    page_number: int,
    table_index: int,
    bbox: list[float] | None,
    markdown_repr: str,
    headers: list[str] | None = None,
    grid: list[dict] | None = None,
    title: str | None = None,
    unit_hint: str | None = None,
    currency_hint: str | None = None,
    period_hint: str | None = None,
) -> dict:
    _ensure_pool()
    with pool.connection() as conn:
        row = conn.execute(
            """INSERT INTO document_tables (
                document_id, page_number, table_index, bbox, title, headers, grid,
                markdown_repr, unit_hint, currency_hint, period_hint
            ) VALUES (
                %s, %s, %s, %s::jsonb, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s
            ) RETURNING *""",
            (
                str(document_id), page_number, table_index,
                psycopg.types.json.Json(bbox) if bbox else None,
                title,
                psycopg.types.json.Json(headers or []),
                psycopg.types.json.Json(grid or []),
                markdown_repr,
                unit_hint, currency_hint, period_hint,
            ),
        ).fetchone()
        return dict(row)


def get_tables_for_document(document_id: str) -> list[dict]:
    _ensure_pool()
    with pool.connection() as conn:
        rows = conn.execute(
            "SELECT * FROM document_tables WHERE document_id = %s ORDER BY page_number ASC, table_index ASC",
            (str(document_id),),
        ).fetchall()
        return [dict(r) for r in rows]


# ── document_chunks ──────────────────────────────────────────────────

def insert_chunk(
    document_id: str,
    page: int,
    chunk_type: str,
    text: str,
    bbox: list | None = None,
    heading: str | None = None,
    ocr_provider: str | None = None,
    section_id: str | None = None,
    table_id: str | None = None,
    reading_order: int = 0,
) -> dict:
    _ensure_pool()
    with pool.connection() as conn:
        row = conn.execute(
            """INSERT INTO document_chunks (
                document_id, page_number, chunk_type, text, bbox, heading, ocr_provider,
                section_id, table_id, reading_order
            ) VALUES (
                %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s
            ) RETURNING *""",
            (
                str(document_id), page, chunk_type, text,
                psycopg.types.json.Json(bbox) if bbox else None,
                heading, ocr_provider,
                str(section_id) if section_id else None,
                str(table_id) if table_id else None,
                reading_order,
            ),
        ).fetchone()
        return dict(row)


def get_chunks_for_document(document_id: str) -> list[dict]:
    _ensure_pool()
    with pool.connection() as conn:
        rows = conn.execute(
            "SELECT id, document_id, page_number AS page, chunk_type, text, bbox, heading, ocr_provider, section_id, table_id, reading_order, created_at FROM document_chunks WHERE document_id = %s ORDER BY page_number ASC, reading_order ASC, created_at ASC",
            (str(document_id),),
        ).fetchall()
        return [dict(r) for r in rows]


# ── entities, periods, metrics ───────────────────────────────────────

def get_or_create_entity(canonical_name: str, legal_name: str | None = None, alias: str | None = None) -> dict:
    _ensure_pool()
    canon = canonical_name.strip()
    with pool.connection() as conn:
        # Check alias first
        if alias:
            alias_clean = alias.strip().lower()
            row = conn.execute("SELECT canonical FROM entity_aliases WHERE alias = %s", (alias_clean,)).fetchone()
            if row:
                canon = row["canonical"]

        # Insert canonical entity
        row = conn.execute(
            """INSERT INTO entities (canonical_name, legal_name)
               VALUES (%s, %s)
               ON CONFLICT (canonical_name) DO UPDATE SET legal_name = COALESCE(EXCLUDED.legal_name, entities.legal_name)
               RETURNING *""",
            (canon, legal_name),
        ).fetchone()

        if alias:
            conn.execute(
                """INSERT INTO entity_aliases (alias, canonical)
                   VALUES (%s, %s)
                   ON CONFLICT (alias) DO UPDATE SET canonical = EXCLUDED.canonical""",
                (alias.strip().lower(), canon),
            )

        return dict(row)


def get_entity_alias(alias: str) -> str | None:
    _ensure_pool()
    with pool.connection() as conn:
        row = conn.execute("SELECT canonical FROM entity_aliases WHERE alias = %s", (alias,)).fetchone()
        return row["canonical"] if row else None


def set_entity_alias(alias: str, canonical: str):
    _ensure_pool()
    with pool.connection() as conn:
        conn.execute(
            """INSERT INTO entity_aliases (alias, canonical)
               VALUES (%s, %s)
               ON CONFLICT (alias) DO UPDATE SET canonical = EXCLUDED.canonical""",
            (alias, canonical),
        )


def get_all_canonical_entities() -> list[str]:
    _ensure_pool()
    with pool.connection() as conn:
        rows = conn.execute("SELECT DISTINCT canonical_name FROM entities").fetchall()
        if not rows:
            rows = conn.execute("SELECT DISTINCT canonical FROM entity_aliases").fetchall()
            return [r["canonical"] for r in rows]
        return [r["canonical_name"] for r in rows]


def get_or_create_period(canonical_period: str, period_type: str = "annual", year: int | None = None, quarter: int | None = None) -> dict:
    _ensure_pool()
    with pool.connection() as conn:
        row = conn.execute(
            """INSERT INTO financial_periods (canonical_period, period_type, year, quarter)
               VALUES (%s, %s, %s, %s)
               ON CONFLICT (canonical_period) DO UPDATE SET period_type = EXCLUDED.period_type
               RETURNING *""",
            (canonical_period, period_type, year, quarter),
        ).fetchone()
        return dict(row)


def get_or_create_metric(canonical_name: str, category: str = "financial", standard_unit: str | None = None, embedding: list[float] | None = None) -> dict:
    _ensure_pool()
    emb_str = json.dumps(embedding) if embedding else None
    with pool.connection() as conn:
        row = conn.execute(
            """INSERT INTO financial_metrics (canonical_name, category, standard_unit, embedding)
               VALUES (%s, %s, %s, %s::vector)
               ON CONFLICT (canonical_name) DO UPDATE SET standard_unit = COALESCE(EXCLUDED.standard_unit, financial_metrics.standard_unit)
               RETURNING *""",
            (canonical_name, category, standard_unit, emb_str),
        ).fetchone()
        return dict(row)


def find_closest_attribute(embedding: list[float], threshold: float = 0.90) -> str | None:
    _ensure_pool()
    emb_str = json.dumps(embedding)
    with pool.connection() as conn:
        # Check financial_metrics first
        row = conn.execute(
            """SELECT canonical_name AS canonical, 1 - (embedding <=> %s::vector) AS similarity
               FROM financial_metrics
               WHERE embedding IS NOT NULL
               ORDER BY embedding <=> %s::vector ASC
               LIMIT 1""",
            (emb_str, emb_str),
        ).fetchone()
        if row and row["similarity"] is not None and row["similarity"] >= threshold:
            return row["canonical"]

        # Fallback to attribute_namespace
        row_legacy = conn.execute(
            """SELECT canonical, 1 - (embedding <=> %s::vector) AS similarity
               FROM attribute_namespace
               WHERE embedding IS NOT NULL
               ORDER BY embedding <=> %s::vector ASC
               LIMIT 1""",
            (emb_str, emb_str),
        ).fetchone()
        if row_legacy and row_legacy["similarity"] is not None and row_legacy["similarity"] >= threshold:
            return row_legacy["canonical"]

        return None


def add_canonical_attribute(canonical: str, embedding: list[float]):
    _ensure_pool()
    emb_str = json.dumps(embedding)
    with pool.connection() as conn:
        conn.execute(
            """INSERT INTO attribute_namespace (canonical, embedding)
               VALUES (%s, %s::vector)
               ON CONFLICT (canonical) DO NOTHING""",
            (canonical, emb_str),
        )
        conn.execute(
            """INSERT INTO financial_metrics (canonical_name, embedding)
               VALUES (%s, %s::vector)
               ON CONFLICT (canonical_name) DO NOTHING""",
            (canonical, emb_str),
        )


# ── facts ────────────────────────────────────────────────────────────

def insert_facts(facts: list[dict]):
    """Insert facts into the facts table."""
    if not facts:
        return
    _ensure_pool()
    with pool.connection() as conn:
        with conn.cursor() as cur:
            for f in facts:
                emb_str = json.dumps(f["embedding"]) if f.get("embedding") else None
                cur.execute(
                    """INSERT INTO facts (
                        document_id, page_number, chunk_id, table_id, entity_id, metric_id, period_id,
                        entity, attribute, entity_canon, attribute_canon, raw_value, norm_value,
                        norm_unit, currency, period, scope, quote, confidence, validation_status,
                        model, prompt_ver, prompt_hash, embedding
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s::vector
                    )""",
                    (
                        str(f["document_id"]),
                        f.get("page_number") or f.get("page"),
                        f.get("chunk_id"),
                        f.get("table_id"),
                        f.get("entity_id"),
                        f.get("metric_id"),
                        f.get("period_id"),
                        f.get("entity"),
                        f.get("attribute"),
                        f.get("entity_canon"),
                        f.get("attribute_canon"),
                        str(f.get("raw_value") or ""),
                        f.get("norm_value"),
                        f.get("norm_unit"),
                        f.get("currency"),
                        f.get("period"),
                        f.get("scope"),
                        str(f.get("quote") or ""),
                        f.get("confidence", 1.0),
                        f.get("validation_status", "valid"),
                        f.get("model"),
                        f.get("prompt_ver"),
                        f.get("prompt_hash"),
                        emb_str,
                    ),
                )


def get_facts_for_document(document_id: str) -> list[dict]:
    _ensure_pool()
    with pool.connection() as conn:
        rows = conn.execute(
            """SELECT f.*, COALESCE(f.page_number, c.page_number) AS page, c.bbox
               FROM facts f
               LEFT JOIN document_chunks c ON f.chunk_id = c.id
               WHERE f.document_id = %s
               ORDER BY f.page_number ASC, f.created_at ASC""",
            (str(document_id),),
        ).fetchall()
        return [dict(r) for r in rows]


def get_fact_with_relations(fact_id: str) -> dict | None:
    _ensure_pool()
    with pool.connection() as conn:
        fact = conn.execute(
            """SELECT f.*, COALESCE(f.page_number, c.page_number) AS page, c.bbox, d.filename AS document_filename
               FROM facts f
               JOIN documents d ON f.document_id = d.id
               LEFT JOIN document_chunks c ON f.chunk_id = c.id
               WHERE f.id = %s""",
            (str(fact_id),),
        ).fetchone()

        if not fact:
            return None

        rel_rows = conn.execute(
            """SELECT r.id AS relation_id, r.relation, r.explanation, r.rules_applied, r.confidence, r.created_at,
                      cf.id AS counterpart_id, cf.entity_canon, cf.attribute_canon, cf.raw_value, cf.norm_value,
                      cf.currency, cf.period, cf.scope, cf.quote,
                      COALESCE(cf.page_number, cc.page_number) AS page, cc.bbox, cd.filename AS document_filename
               FROM fact_relations r
               JOIN facts cf ON (CASE WHEN r.fact_a = %s::uuid THEN r.fact_b ELSE r.fact_a END) = cf.id
               JOIN documents cd ON cf.document_id = cd.id
               LEFT JOIN document_chunks cc ON cf.chunk_id = cc.id
               WHERE r.fact_a = %s::uuid OR r.fact_b = %s::uuid
               ORDER BY r.created_at DESC""",
            (str(fact_id), str(fact_id), str(fact_id)),
        ).fetchall()

        res = dict(fact)
        res["relations"] = [dict(r) for r in rel_rows]
        return res


# ── evidence & provenance ────────────────────────────────────────────

def insert_evidence_snippet(
    document_id: str,
    page: int,
    evidence_type: str,
    content: str,
    bbox: list[float] | None = None,
    table_coord: dict | None = None,
    model_id: str | None = None,
    prompt_hash: str | None = None,
) -> dict:
    """Insert or retrieve deduplicated evidence record using SHA-256 content hash."""
    import hashlib
    _ensure_pool()
    content_h = hashlib.sha256(f"{content}|{page}|{evidence_type}".encode("utf-8")).hexdigest()

    with pool.connection() as conn:
        row = conn.execute(
            """INSERT INTO evidence (
                document_id, page, evidence_type, content_hash, content, bbox, table_ref, model_id, prompt_hash
            ) VALUES (
                %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s
            ) ON CONFLICT (content_hash) DO UPDATE
            SET content = EXCLUDED.content
            RETURNING *""",
            (
                str(document_id), page, evidence_type, content_h, content,
                psycopg.types.json.Json(bbox) if bbox else None,
                psycopg.types.json.Json(table_coord) if table_coord else None,
                model_id, prompt_hash,
            ),
        ).fetchone()
        return dict(row)


def link_fact_to_evidence(fact_id: str, evidence_id: str, role: str = "source"):
    _ensure_pool()
    with pool.connection() as conn:
        conn.execute(
            """INSERT INTO fact_evidence (fact_id, evidence_id, role)
               VALUES (%s, %s, %s)
               ON CONFLICT DO NOTHING""",
            (str(fact_id), str(evidence_id), role),
        )


def get_evidence_for_fact(fact_id: str) -> list[dict]:
    _ensure_pool()
    with pool.connection() as conn:
        rows = conn.execute(
            """SELECT e.*, fe.role
               FROM evidence e
               JOIN fact_evidence fe ON fe.evidence_id = e.id
               WHERE fe.fact_id = %s
               ORDER BY e.created_at ASC""",
            (str(fact_id),),
        ).fetchall()
        return [dict(r) for r in rows]


# ── reconciliation & relations ───────────────────────────────────────

def get_candidate_pairs_for_reconciliation(
    document_id: str,
    semantic_threshold: float = 0.86,
    include_intra_document: bool = True,
) -> list[tuple[dict, dict]]:
    """Retrieve candidate pairs for reconciliation (both cross-document and intra-document tie-outs)."""
    _ensure_pool()
    with pool.connection() as conn:
        doc_filter = "" if include_intra_document else "AND f_other.document_id != f_this.document_id"

        # 1. Exact match pairs on (entity_canon, attribute_canon)
        exact_rows = conn.execute(
            f"""SELECT row_to_json(f_this) AS this_fact, row_to_json(f_other) AS other_fact
               FROM facts f_this
               JOIN facts f_other
                 ON f_this.entity_canon = f_other.entity_canon
                AND f_this.attribute_canon = f_other.attribute_canon
                AND f_other.id != f_this.id
                {doc_filter}
               WHERE f_this.document_id = %s
                 AND NOT EXISTS (
                     SELECT 1 FROM fact_relations r
                     WHERE (r.fact_a = f_this.id AND r.fact_b = f_other.id)
                        OR (r.fact_a = f_other.id AND r.fact_b = f_this.id)
                 )""",
            (str(document_id),),
        ).fetchall()

        # 2. Semantic sweep pairs (different attribute_canon, high cosine similarity)
        semantic_rows = conn.execute(
            f"""SELECT row_to_json(f_this) AS this_fact, row_to_json(f_other) AS other_fact
               FROM facts f_this
               JOIN facts f_other
                 ON f_other.id != f_this.id
                AND f_other.attribute_canon IS DISTINCT FROM f_this.attribute_canon
                AND 1 - (f_other.embedding <=> f_this.embedding) > %s
                {doc_filter}
               WHERE f_this.document_id = %s
                 AND f_this.embedding IS NOT NULL
                 AND f_other.embedding IS NOT NULL
                 AND NOT EXISTS (
                     SELECT 1 FROM fact_relations r
                     WHERE (r.fact_a = f_this.id AND r.fact_b = f_other.id)
                        OR (r.fact_a = f_other.id AND r.fact_b = f_this.id)
                 )""",
            (semantic_threshold, str(document_id)),
        ).fetchall()

    seen_pairs = set()
    candidate_pairs = []

    for r in exact_rows + semantic_rows:
        fa = r["this_fact"]
        fb = r["other_fact"]
        pair_key = tuple(sorted([str(fa["id"]), str(fb["id"])]))
        if pair_key not in seen_pairs:
            seen_pairs.add(pair_key)
            candidate_pairs.append((fa, fb))

    return candidate_pairs


def insert_fact_relation(
    fact_a: str,
    fact_b: str,
    relation: str,
    explanation: str,
    rules_applied: list[str],
    confidence: float,
) -> dict:
    _ensure_pool()
    with pool.connection() as conn:
        row = conn.execute(
            """INSERT INTO fact_relations (fact_a, fact_b, relation, explanation, rules_applied, confidence)
               VALUES (%s, %s, %s, %s, %s::jsonb, %s)
               RETURNING *""",
            (
                str(fact_a),
                str(fact_b),
                relation,
                explanation,
                psycopg.types.json.Json(rules_applied),
                confidence,
            ),
        ).fetchone()
        return dict(row)


def get_relations(relation_type: str | None = None, document_id: str | None = None) -> list[dict]:
    _ensure_pool()
    query = """
        SELECT r.id, r.relation, r.explanation, r.rules_applied, r.confidence, r.created_at,
               fa.id AS a_id, fa.entity_canon AS a_entity, fa.attribute_canon AS a_attribute,
               fa.raw_value AS a_value, fa.norm_value AS a_norm_value, fa.quote AS a_quote,
               fa.document_id AS a_document_id, da.filename AS a_filename,
               fb.id AS b_id, fb.entity_canon AS b_entity, fb.attribute_canon AS b_attribute,
               fb.raw_value AS b_value, fb.norm_value AS b_norm_value, fb.quote AS b_quote,
               fb.document_id AS b_document_id, db.filename AS b_filename
        FROM fact_relations r
        JOIN facts fa ON r.fact_a = fa.id
        JOIN facts fb ON r.fact_b = fb.id
        JOIN documents da ON fa.document_id = da.id
        JOIN documents db ON fb.document_id = db.id
        WHERE (%s::text IS NULL OR r.relation = %s)
          AND (%s::text IS NULL OR fa.document_id = %s::uuid OR fb.document_id = %s::uuid)
        ORDER BY r.created_at DESC
    """
    with pool.connection() as conn:
        rows = conn.execute(
            query,
            (relation_type, relation_type, document_id, document_id, document_id),
        ).fetchall()
        return [dict(r) for r in rows]


# ── matrix & search ──────────────────────────────────────────────────

def get_matrix_data() -> dict:
    """Returns {entities: [...], attributes: [...], cells: {entity|attribute: [fact_ids]}, cell_badges: {...}}."""
    _ensure_pool()
    query = """
        SELECT f.id, f.entity_canon, f.attribute_canon,
               ARRAY_AGG(DISTINCT r.relation) FILTER (WHERE r.relation IS NOT NULL) AS relations
        FROM facts f
        LEFT JOIN fact_relations r ON (f.id = r.fact_a OR f.id = r.fact_b)
        WHERE f.entity_canon IS NOT NULL AND f.attribute_canon IS NOT NULL
        GROUP BY f.id, f.entity_canon, f.attribute_canon
        ORDER BY f.entity_canon, f.attribute_canon
    """
    with pool.connection() as conn:
        rows = conn.execute(query).fetchall()

    entities_set = set()
    attributes_set = set()
    cells: dict[str, list[str]] = {}
    cell_relations: dict[str, set[str]] = {}

    for r in rows:
        ent = r["entity_canon"]
        att = r["attribute_canon"]
        fact_id = str(r["id"])
        entities_set.add(ent)
        attributes_set.add(att)

        key = f"{ent}|{att}"
        if key not in cells:
            cells[key] = []
            cell_relations[key] = set()

        cells[key].append(fact_id)
        if r.get("relations"):
            for rel in r["relations"]:
                if rel:
                    cell_relations[key].add(rel)

    cell_badges: dict[str, str | None] = {}
    cell_details: dict[str, dict] = {}

    for key, fact_ids in cells.items():
        rels = cell_relations.get(key, set())
        if "contradicts" in rels:
            badge = "contradicts"
        elif "contextual_variance" in rels:
            badge = "contextual_variance"
        elif "needs_review" in rels:
            badge = "needs_review"
        elif "corroborates" in rels:
            badge = "corroborates"
        else:
            badge = None

        cell_badges[key] = badge
        cell_details[key] = {
            "fact_ids": fact_ids,
            "badge": badge,
        }

    return {
        "entities": sorted(list(entities_set)),
        "attributes": sorted(list(attributes_set)),
        "cells": cells,
        "cell_badges": cell_badges,
        "cell_details": cell_details,
        "cell_facts": cells,
    }


def search_facts(
    document_id: str | None = None,
    entity_canon: str | None = None,
    attribute_canon: str | None = None,
    query_vector: list[float] | None = None,
    limit: int = 50,
) -> list[dict]:
    _ensure_pool()
    has_valid_vector = query_vector and any(abs(v) > 1e-6 for v in query_vector)
    with pool.connection() as conn:
        if has_valid_vector:
            emb_str = json.dumps(query_vector)
            where_parts = ["f.embedding IS NOT NULL"]
            params = [emb_str]
            if document_id:
                where_parts.append("f.document_id = %s::uuid")
                params.append(document_id)
            if entity_canon:
                where_parts.append("f.entity_canon = %s")
                params.append(entity_canon)
            if attribute_canon:
                where_parts.append("f.attribute_canon = %s")
                params.append(attribute_canon)
            params.extend([emb_str, limit])

            sql = f"""
                SELECT f.*, COALESCE(f.page_number, c.page_number) AS page, c.bbox, d.filename,
                       (1 - (f.embedding <=> %s::vector)) AS similarity,
                       COALESCE((
                           SELECT ARRAY_AGG(DISTINCT r.relation)
                           FROM fact_relations r
                           WHERE r.fact_a = f.id OR r.fact_b = f.id
                       ), ARRAY[]::text[]) AS relations_summary
                FROM facts f
                JOIN documents d ON f.document_id = d.id
                LEFT JOIN document_chunks c ON f.chunk_id = c.id
                WHERE {' AND '.join(where_parts)}
                ORDER BY f.embedding <=> %s::vector ASC
                LIMIT %s
            """
            rows = conn.execute(sql, tuple(params)).fetchall()
        else:
            where_parts = ["1=1"]
            params = []
            if document_id:
                where_parts.append("f.document_id = %s::uuid")
                params.append(document_id)
            if entity_canon:
                where_parts.append("f.entity_canon = %s")
                params.append(entity_canon)
            if attribute_canon:
                where_parts.append("f.attribute_canon = %s")
                params.append(attribute_canon)
            params.append(limit)

            sql = f"""
                SELECT f.*, COALESCE(f.page_number, c.page_number) AS page, c.bbox, d.filename,
                       1.0 AS similarity,
                       COALESCE((
                           SELECT ARRAY_AGG(DISTINCT r.relation)
                           FROM fact_relations r
                           WHERE r.fact_a = f.id OR r.fact_b = f.id
                       ), ARRAY[]::text[]) AS relations_summary
                FROM facts f
                JOIN documents d ON f.document_id = d.id
                LEFT JOIN document_chunks c ON f.chunk_id = c.id
                WHERE {' AND '.join(where_parts)}
                ORDER BY f.created_at DESC
                LIMIT %s
            """
            rows = conn.execute(sql, tuple(params)).fetchall()

        return [dict(r) for r in rows]


def search_facts_keyword(tokens: list[str], limit: int = 8) -> list[dict]:
    if not tokens:
        return []
    _ensure_pool()
    with pool.connection() as conn:
        clauses = []
        params: list[str] = []
        for t in tokens:
            pat = f"%{t}%"
            clauses.append("(f.entity ILIKE %s OR f.attribute ILIKE %s OR f.entity_canon ILIKE %s OR f.attribute_canon ILIKE %s OR f.raw_value ILIKE %s OR f.quote ILIKE %s)")
            params.extend([pat, pat, pat, pat, pat, pat])

        where_clause = " OR ".join(clauses)
        sql = f"""
            SELECT f.*, COALESCE(f.page_number, c.page_number) AS page, c.bbox, d.filename,
                   1.0 AS similarity,
                   COALESCE((
                       SELECT ARRAY_AGG(DISTINCT r.relation)
                       FROM fact_relations r
                       WHERE r.fact_a = f.id OR r.fact_b = f.id
                   ), ARRAY[]::text[]) AS relations_summary
            FROM facts f
            JOIN documents d ON f.document_id = d.id
            LEFT JOIN document_chunks c ON f.chunk_id = c.id
            WHERE {where_clause}
            ORDER BY f.confidence DESC
            LIMIT %s
        """
        params.append(limit)
        rows = conn.execute(sql, tuple(params)).fetchall()
        return [dict(r) for r in rows]


def get_fact_lineage_audit(fact_id: str) -> list[dict]:
    _ensure_pool()
    with pool.connection() as conn:
        fact = conn.execute(
            """SELECT f.id, f.document_id, f.chunk_id, COALESCE(f.page_number, c.page_number) AS page
               FROM facts f
               LEFT JOIN document_chunks c ON f.chunk_id = c.id
               WHERE f.id = %s""",
            (str(fact_id),),
        ).fetchone()

        if not fact:
            return []

        doc_id = str(fact["document_id"])
        chunk_id = str(fact["chunk_id"]) if fact["chunk_id"] else None
        page = fact.get("page")

        all_rows = conn.execute(
            """SELECT * FROM audit
               WHERE (target->>'fact_id' = %s)
                  OR (target->>'chunk_id' = %s)
                  OR (target->>'document_id' = %s)
                  OR (meta::text ILIKE %s)
               ORDER BY at ASC""",
            (str(fact_id), chunk_id, doc_id, f"%{fact_id}%"),
        ).fetchall()

        return [dict(r) for r in all_rows]


def audit(action: str, target: dict | None = None, meta: dict | None = None, actor: str = "system"):
    try:
        _ensure_pool()
        with pool.connection() as conn:
            conn.execute(
                """INSERT INTO audit (actor, action, target, meta)
                   VALUES (%s, %s, %s::jsonb, %s::jsonb)""",
                (actor, action, psycopg.types.json.Json(target), psycopg.types.json.Json(meta)),
            )
    except Exception:
        pass


# ── durable transactional jobs queue ─────────────────────────────────

def new_job(document_id: str | uuid.UUID, stage: str = "queued", status: str = "pending") -> dict:
    _ensure_pool()
    with pool.connection() as conn:
        row = conn.execute(
            """INSERT INTO jobs (document_id, stage, status, progress, heartbeat_at, updated_at)
               VALUES (%s, %s, %s, 0.0, %s, %s)
               RETURNING *""",
            (str(document_id), stage, status, _now(), _now()),
        ).fetchone()
        return dict(row)


def set_job(job_id: str | uuid.UUID, *, stage: str, status: str, error: str | None = None, progress: float | None = None):
    _ensure_pool()
    with pool.connection() as conn:
        if progress is not None:
            conn.execute(
                """UPDATE jobs SET stage = %s, status = %s, error = %s, progress = %s, heartbeat_at = %s, updated_at = %s
                   WHERE id = %s""",
                (stage, status, error, progress, _now(), _now(), str(job_id)),
            )
        else:
            conn.execute(
                """UPDATE jobs SET stage = %s, status = %s, error = %s, heartbeat_at = %s, updated_at = %s
                   WHERE id = %s""",
                (stage, status, error, _now(), _now(), str(job_id)),
            )


def claim_next_job() -> dict | None:
    """Atomically claim the next pending or stale job using FOR UPDATE SKIP LOCKED."""
    _ensure_pool()
    with pool.connection() as conn:
        row = conn.execute(
            """UPDATE jobs
               SET status = 'running',
                   attempts = attempts + 1,
                   heartbeat_at = now(),
                   updated_at = now()
               WHERE id = (
                   SELECT id FROM jobs
                   WHERE (status = 'pending')
                      OR (status = 'running' AND heartbeat_at < now() - interval '5 minutes' AND attempts < max_attempts)
                   ORDER BY created_at ASC
                   FOR UPDATE SKIP LOCKED
                   LIMIT 1
               )
               RETURNING *"""
        ).fetchone()
        return dict(row) if row else None


def update_job_checkpoint(
    job_id: str,
    stage: str,
    progress: float,
    checkpoint_data: dict | None = None,
):
    _ensure_pool()
    with pool.connection() as conn:
        conn.execute(
            """UPDATE jobs
               SET stage = %s,
                   progress = %s,
                   checkpoint_data = COALESCE(%s::jsonb, checkpoint_data),
                   heartbeat_at = now(),
                   updated_at = now()
               WHERE id = %s""",
            (stage, progress, psycopg.types.json.Json(checkpoint_data) if checkpoint_data else None, str(job_id)),
        )


def heartbeat_job(job_id: str):
    _ensure_pool()
    with pool.connection() as conn:
        conn.execute("UPDATE jobs SET heartbeat_at = now() WHERE id = %s", (str(job_id),))


def complete_job(job_id: str):
    _ensure_pool()
    with pool.connection() as conn:
        conn.execute(
            """UPDATE jobs
               SET stage = 'done',
                   status = 'done',
                   progress = 1.0,
                   error = NULL,
                   updated_at = now()
               WHERE id = %s""",
            (str(job_id),),
        )


def fail_job(job_id: str, error: str, retry: bool = True):
    _ensure_pool()
    with pool.connection() as conn:
        job = conn.execute("SELECT attempts, max_attempts FROM jobs WHERE id = %s", (str(job_id),)).fetchone()
        if job and retry and job["attempts"] < job["max_attempts"]:
            conn.execute(
                """UPDATE jobs
                   SET status = 'pending',
                       error = %s,
                       updated_at = now()
                   WHERE id = %s""",
                (error, str(job_id)),
            )
        else:
            conn.execute(
                """UPDATE jobs
                   SET status = 'failed',
                       stage = 'failed',
                       error = %s,
                       updated_at = now()
                   WHERE id = %s""",
                (error, str(job_id)),
            )


def get_job(job_id: str | uuid.UUID) -> dict | None:
    _ensure_pool()
    with pool.connection() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = %s", (str(job_id),)).fetchone()
        return dict(row) if row else None


def get_job_for_document(document_id: str | uuid.UUID) -> dict | None:
    _ensure_pool()
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT * FROM jobs WHERE document_id = %s ORDER BY updated_at DESC LIMIT 1",
            (str(document_id),),
        ).fetchone()
        return dict(row) if row else None


# ── review queue ─────────────────────────────────────────────────────

def create_review_item(
    fact_id: str | None = None,
    relation_id: str | None = None,
    reason: str = "needs_review",
    details: str = "",
) -> dict:
    _ensure_pool()
    with pool.connection() as conn:
        row = conn.execute(
            """INSERT INTO review_queue (fact_id, relation_id, reason, status, decision)
               VALUES (%s, %s, %s, 'pending', %s)
               RETURNING *""",
            (str(fact_id) if fact_id else None, str(relation_id) if relation_id else None, reason, details),
        ).fetchone()
        return dict(row)


def get_review_queue(status: str = "pending", limit: int = 50) -> list[dict]:
    _ensure_pool()
    with pool.connection() as conn:
        rows = conn.execute(
            """SELECT rq.*, f.entity_canon, f.attribute_canon, f.raw_value,
                      f.confidence AS fact_confidence, f.quote,
                      d.filename, COALESCE(f.page_number, c.page_number) AS page
               FROM review_queue rq
               LEFT JOIN facts f ON rq.fact_id = f.id
               LEFT JOIN documents d ON f.document_id = d.id
               LEFT JOIN document_chunks c ON f.chunk_id = c.id
               WHERE (%s = '' OR rq.status = %s)
               ORDER BY rq.created_at DESC
               LIMIT %s""",
            (status, status, limit),
        ).fetchall()
        return [dict(r) for r in rows]


def resolve_review(review_id: str, status: str, reviewer: str = "system", decision: str = "") -> dict | None:
    _ensure_pool()
    with pool.connection() as conn:
        row = conn.execute(
            """UPDATE review_queue
               SET status = %s, reviewer = %s, decision = %s, reviewed_at = %s
               WHERE id = %s
               RETURNING *""",
            (status, reviewer, decision, _now(), str(review_id)),
        ).fetchone()
        return dict(row) if row else None


def get_review_stats() -> dict:
    _ensure_pool()
    with pool.connection() as conn:
        rows = conn.execute(
            """SELECT status, COUNT(*) AS count
               FROM review_queue
               GROUP BY status"""
        ).fetchall()
    stats = {"pending": 0, "approved": 0, "rejected": 0, "deferred": 0}
    for r in rows:
        stats[r["status"]] = r["count"]
    return stats


# ── calculations ─────────────────────────────────────────────────────

def get_calculations_for_fact(fact_id: str) -> list[dict]:
    _ensure_pool()
    with pool.connection() as conn:
        rows = conn.execute(
            "SELECT * FROM calculations WHERE fact_id = %s ORDER BY created_at ASC",
            (str(fact_id),),
        ).fetchall()
        return [dict(r) for r in rows]


# ── anomalies ────────────────────────────────────────────────────────

def get_anomalies_for_document(document_id: str) -> list[dict]:
    _ensure_pool()
    with pool.connection() as conn:
        rows = conn.execute(
            """SELECT rq.*, f.entity_canon, f.attribute_canon, f.raw_value,
                      f.norm_value, f.period, f.quote, d.filename, COALESCE(f.page_number, c.page_number) AS page
               FROM review_queue rq
               JOIN facts f ON rq.fact_id = f.id
               JOIN documents d ON f.document_id = d.id
               LEFT JOIN document_chunks c ON f.chunk_id = c.id
               WHERE f.document_id = %s::uuid
                 AND rq.reason LIKE 'anomaly:%%'
               ORDER BY rq.created_at DESC""",
            (str(document_id),),
        ).fetchall()
        return [dict(r) for r in rows]


# ── findings (analysis layer) ────────────────────────────────────────

def insert_finding(
    category: str,
    severity: str,
    title: str,
    description: str,
    fact_ids: list[str] | None = None,
    relation_ids: list[str] | None = None,
    evidence_ids: list[str] | None = None,
    document_ids: list[str] | None = None,
    details: dict | None = None,
    explanation: str | None = None,
    case_id: str | None = None,
) -> dict:
    _ensure_pool()
    with pool.connection() as conn:
        row = conn.execute(
            """INSERT INTO findings (
                case_id, category, severity, title, description, explanation,
                fact_ids, relation_ids, evidence_ids, document_ids, details
            ) VALUES (
                %s, %s, %s, %s, %s, %s,
                %s::uuid[], %s::uuid[], %s::uuid[], %s::uuid[], %s::jsonb
            ) RETURNING *""",
            (
                str(case_id) if case_id else None,
                category, severity, title, description, explanation,
                fact_ids or [],
                relation_ids or [],
                evidence_ids or [],
                document_ids or [],
                psycopg.types.json.Json(details or {}),
            ),
        ).fetchone()
        return dict(row)


def get_findings(
    category: str | None = None,
    severity: str | None = None,
    status: str | None = None,
    document_id: str | None = None,
    limit: int = 100,
) -> list[dict]:
    _ensure_pool()
    where_parts = ["1=1"]
    params: list[Any] = []

    if category:
        where_parts.append("f.category = %s")
        params.append(category)
    if severity:
        where_parts.append("f.severity = %s")
        params.append(severity)
    if status:
        where_parts.append("f.status = %s")
        params.append(status)
    if document_id:
        where_parts.append("%s::uuid = ANY(f.document_ids)")
        params.append(document_id)

    params.append(limit)

    sql = f"""
        SELECT * FROM findings f
        WHERE {' AND '.join(where_parts)}
        ORDER BY
            CASE f.severity
                WHEN 'critical' THEN 1
                WHEN 'high' THEN 2
                WHEN 'medium' THEN 3
                WHEN 'low' THEN 4
                WHEN 'info' THEN 5
            END ASC,
            f.created_at DESC
        LIMIT %s
    """
    with pool.connection() as conn:
        rows = conn.execute(sql, tuple(params)).fetchall()
        return [dict(r) for r in rows]


def get_finding(finding_id: str) -> dict | None:
    _ensure_pool()
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT * FROM findings WHERE id = %s", (str(finding_id),)
        ).fetchone()
        return dict(row) if row else None


def update_finding_status(finding_id: str, status: str) -> dict | None:
    _ensure_pool()
    with pool.connection() as conn:
        row = conn.execute(
            "UPDATE findings SET status = %s WHERE id = %s RETURNING *",
            (status, str(finding_id)),
        ).fetchone()
        return dict(row) if row else None


def update_finding_explanation(finding_id: str, explanation: str):
    _ensure_pool()
    with pool.connection() as conn:
        conn.execute(
            "UPDATE findings SET explanation = %s WHERE id = %s",
            (explanation, str(finding_id)),
        )


def get_findings_summary() -> dict:
    _ensure_pool()
    with pool.connection() as conn:
        rows = conn.execute(
            """SELECT category, severity, COUNT(*) AS count
               FROM findings
               WHERE status = 'open'
               GROUP BY category, severity
               ORDER BY category, severity"""
        ).fetchall()
    summary: dict[str, dict[str, int]] = {}
    totals = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0, "total": 0}
    for r in rows:
        cat = r["category"]
        sev = r["severity"]
        cnt = r["count"]
        if cat not in summary:
            summary[cat] = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0, "total": 0}
        summary[cat][sev] = cnt
        summary[cat]["total"] += cnt
        totals[sev] = totals.get(sev, 0) + cnt
        totals["total"] += cnt
    return {"by_category": summary, "totals": totals}


def get_facts_grouped_for_analysis(
    document_ids: list[str] | None = None,
) -> list[dict]:
    """Get facts grouped by (entity_canon, attribute_canon, period) for cross-document analysis."""
    _ensure_pool()
    with pool.connection() as conn:
        if document_ids:
            placeholders = ",".join(["%s"] * len(document_ids))
            sql = f"""
                SELECT f.*, d.filename,
                       COALESCE(f.page_number, c.page_number) AS page, c.bbox
                FROM facts f
                JOIN documents d ON f.document_id = d.id
                LEFT JOIN document_chunks c ON f.chunk_id = c.id
                WHERE f.document_id IN ({placeholders})
                  AND f.entity_canon IS NOT NULL
                  AND f.attribute_canon IS NOT NULL
                ORDER BY f.entity_canon, f.attribute_canon, f.period
            """
            rows = conn.execute(sql, tuple(str(d) for d in document_ids)).fetchall()
        else:
            rows = conn.execute(
                """SELECT f.*, d.filename,
                          COALESCE(f.page_number, c.page_number) AS page, c.bbox
                   FROM facts f
                   JOIN documents d ON f.document_id = d.id
                   LEFT JOIN document_chunks c ON f.chunk_id = c.id
                   WHERE f.entity_canon IS NOT NULL
                     AND f.attribute_canon IS NOT NULL
                   ORDER BY f.entity_canon, f.attribute_canon, f.period"""
            ).fetchall()
        return [dict(r) for r in rows]


def get_distinct_metrics_by_entity_period(
    document_ids: list[str] | None = None,
) -> list[dict]:
    """Get distinct (entity, period, document) → set of attribute_canons for missing disclosure detection."""
    _ensure_pool()
    with pool.connection() as conn:
        if document_ids:
            placeholders = ",".join(["%s"] * len(document_ids))
            sql = f"""
                SELECT f.entity_canon, f.period, f.document_id, d.filename,
                       ARRAY_AGG(DISTINCT f.attribute_canon) AS metrics
                FROM facts f
                JOIN documents d ON f.document_id = d.id
                WHERE f.document_id IN ({placeholders})
                  AND f.entity_canon IS NOT NULL
                  AND f.attribute_canon IS NOT NULL
                  AND f.period IS NOT NULL
                GROUP BY f.entity_canon, f.period, f.document_id, d.filename
            """
            rows = conn.execute(sql, tuple(str(d) for d in document_ids)).fetchall()
        else:
            rows = conn.execute(
                """SELECT f.entity_canon, f.period, f.document_id, d.filename,
                          ARRAY_AGG(DISTINCT f.attribute_canon) AS metrics
                   FROM facts f
                   JOIN documents d ON f.document_id = d.id
                   WHERE f.entity_canon IS NOT NULL
                     AND f.attribute_canon IS NOT NULL
                     AND f.period IS NOT NULL
                   GROUP BY f.entity_canon, f.period, f.document_id, d.filename"""
            ).fetchall()
        return [dict(r) for r in rows]

