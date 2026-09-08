"""Database helpers — psycopg3 pool, thin wrappers, nothing more.

DESIGN NOTES:
- sha256 dedupe enables incremental ingestion later
- jobs table is the queue (no Redis on free tier)
- R2 because Render disk is ephemeral
- audit exists from day one
"""

import os
import uuid
from datetime import datetime, timezone

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

DATABASE_URL = os.environ["DATABASE_URL"]

pool = ConnectionPool(DATABASE_URL, min_size=1, max_size=5, kwargs={"row_factory": dict_row})


def _now():
    return datetime.now(timezone.utc)


def q(sql: str, params: tuple | list | None = None) -> list[dict]:
    """Execute raw SQL query with parameters using the connection pool."""
    with pool.connection() as conn:
        return conn.execute(sql, params or ()).fetchall()


# ── documents ────────────────────────────────────────────────────────

def new_document(filename: str, sha256: str, r2_key: str) -> dict:

    with pool.connection() as conn:
        row = conn.execute(
            """INSERT INTO documents (filename, sha256, r2_key)
               VALUES (%s, %s, %s)
               RETURNING *""",
            (filename, sha256, r2_key),
        ).fetchone()
        return row


insert_document = new_document


def get_document_by_sha(sha256: str) -> dict | None:
    with pool.connection() as conn:
        return conn.execute(
            "SELECT * FROM documents WHERE sha256 = %s", (sha256,)
        ).fetchone()


def list_documents() -> list[dict]:
    with pool.connection() as conn:
        return conn.execute(
            "SELECT * FROM documents ORDER BY created_at DESC"
        ).fetchall()


def update_document_page_count(document_id: str, page_count: int):
    with pool.connection() as conn:
        conn.execute(
            "UPDATE documents SET page_count = %s WHERE id = %s",
            (page_count, document_id),
        )


# ── pages ────────────────────────────────────────────────────────────

def insert_page(document_id: str, page: int, width: float | None, height: float | None, png_key: str, route: str) -> dict:
    with pool.connection() as conn:
        return conn.execute(
            """INSERT INTO pages (document_id, page, width, height, png_key, route)
               VALUES (%s, %s, %s, %s, %s, %s)
               RETURNING *""",
            (str(document_id), page, width, height, png_key, route),
        ).fetchone()


def get_page(document_id: str, page: int) -> dict | None:
    with pool.connection() as conn:
        return conn.execute(
            "SELECT * FROM pages WHERE document_id = %s AND page = %s",
            (str(document_id), page),
        ).fetchone()


def update_page_route(document_id: str, page: int, route: str):
    with pool.connection() as conn:
        conn.execute(
            "UPDATE pages SET route = %s WHERE document_id = %s AND page = %s",
            (route, str(document_id), page),
        )


# ── jobs ─────────────────────────────────────────────────────────────



def new_job(document_id: uuid.UUID, stage: str = "queued", status: str = "pending") -> dict:
    with pool.connection() as conn:
        return conn.execute(
            """INSERT INTO jobs (document_id, stage, status, updated_at)
               VALUES (%s, %s, %s, %s)
               RETURNING *""",
            (str(document_id), stage, status, _now()),
        ).fetchone()


def set_job(job_id: uuid.UUID, *, stage: str, status: str, error: str | None = None):
    with pool.connection() as conn:
        conn.execute(
            """UPDATE jobs SET stage = %s, status = %s, error = %s, updated_at = %s
               WHERE id = %s""",
            (stage, status, error, _now(), str(job_id)),
        )


def get_job(job_id: uuid.UUID) -> dict | None:
    with pool.connection() as conn:
        return conn.execute(
            "SELECT * FROM jobs WHERE id = %s", (str(job_id),)
        ).fetchone()


def get_job_for_document(document_id: uuid.UUID) -> dict | None:
    with pool.connection() as conn:
        return conn.execute(
            "SELECT * FROM jobs WHERE document_id = %s ORDER BY updated_at DESC LIMIT 1",
            (str(document_id),),
        ).fetchone()


# ── chunks ───────────────────────────────────────────────────────────

def insert_chunk(document_id: str, page: int, chunk_type: str, text: str,
                 bbox: list | None, heading: str | None, ocr_provider: str | None):
    with pool.connection() as conn:
        conn.execute(
            """INSERT INTO chunks (document_id, page, chunk_type, text, bbox, heading, ocr_provider)
               VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s)""",
            (document_id, page, chunk_type, text,
             psycopg.types.json.Json(bbox) if bbox else None,
             heading, ocr_provider),
        )


def get_chunks_for_document(document_id: str) -> list[dict]:
    with pool.connection() as conn:
        return conn.execute(
            "SELECT * FROM chunks WHERE document_id = %s ORDER BY page ASC, created_at ASC",
            (str(document_id),),
        ).fetchall()


# ── facts ────────────────────────────────────────────────────────────

def insert_facts(facts: list[dict]):
    if not facts:
        return
    import json
    with pool.connection() as conn:
        with conn.cursor() as cur:
            for f in facts:
                emb_str = json.dumps(f["embedding"]) if f.get("embedding") else None
                cur.execute(
                    """INSERT INTO facts (
                        chunk_id, document_id, entity, attribute, entity_canon, attribute_canon,
                        raw_value, norm_value, norm_unit, currency, period, scope,
                        quote, confidence, model, prompt_ver, embedding
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s::vector
                    )""",
                    (
                        f.get("chunk_id"), str(f["document_id"]), f.get("entity"), f.get("attribute"),
                        f.get("entity_canon"), f.get("attribute_canon"), f.get("raw_value"),
                        f.get("norm_value"), f.get("norm_unit"), f.get("currency"), f.get("period"),
                        f.get("scope"), f.get("quote"), f.get("confidence"), f.get("model"),
                        f.get("prompt_ver"), emb_str,
                    ),
                )


def get_facts_for_document(document_id: str) -> list[dict]:
    with pool.connection() as conn:
        return conn.execute(
            "SELECT * FROM facts WHERE document_id = %s ORDER BY created_at ASC",
            (str(document_id),),
        ).fetchall()


# ── entity aliases ───────────────────────────────────────────────────

def get_entity_alias(alias: str) -> str | None:
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT canonical FROM entity_aliases WHERE alias = %s", (alias,)
        ).fetchone()
        return row["canonical"] if row else None


def get_all_canonical_entities() -> list[str]:
    with pool.connection() as conn:
        rows = conn.execute("SELECT DISTINCT canonical FROM entity_aliases").fetchall()
        return [r["canonical"] for r in rows]


def set_entity_alias(alias: str, canonical: str):
    with pool.connection() as conn:
        conn.execute(
            """INSERT INTO entity_aliases (alias, canonical)
               VALUES (%s, %s)
               ON CONFLICT (alias) DO UPDATE SET canonical = EXCLUDED.canonical""",
            (alias, canonical),
        )


# ── attribute namespace ──────────────────────────────────────────────

def find_closest_attribute(embedding: list[float], threshold: float = 0.90) -> str | None:
    import json
    emb_str = json.dumps(embedding)
    with pool.connection() as conn:
        row = conn.execute(
            """SELECT canonical, 1 - (embedding <=> %s::vector) AS similarity
               FROM attribute_namespace
               ORDER BY embedding <=> %s::vector ASC
               LIMIT 1""",
            (emb_str, emb_str),
        ).fetchone()
        if row and row["similarity"] is not None and row["similarity"] >= threshold:
            return row["canonical"]
        return None


def add_canonical_attribute(canonical: str, embedding: list[float]):
    import json
    emb_str = json.dumps(embedding)
    with pool.connection() as conn:
        conn.execute(
            """INSERT INTO attribute_namespace (canonical, embedding)
               VALUES (%s, %s::vector)
               ON CONFLICT (canonical) DO NOTHING""",
            (canonical, emb_str),
        )


# ── fact relations & reconciliation ──────────────────────────────────

def get_candidate_pairs_for_reconciliation(document_id: str, semantic_threshold: float = 0.86) -> list[tuple[dict, dict]]:
    """Retrieve candidate pairs between this document's facts and other documents' facts."""
    with pool.connection() as conn:
        # 1. Exact match pairs on (entity_canon, attribute_canon)
        exact_rows = conn.execute(
            """SELECT row_to_json(f_this) AS this_fact, row_to_json(f_other) AS other_fact
               FROM facts f_this
               JOIN facts f_other
                 ON f_this.entity_canon = f_other.entity_canon
                AND f_this.attribute_canon = f_other.attribute_canon
                AND f_other.document_id != f_this.document_id
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
            """SELECT row_to_json(f_this) AS this_fact, row_to_json(f_other) AS other_fact
               FROM facts f_this
               JOIN facts f_other
                 ON f_other.document_id != f_this.document_id
                AND f_other.attribute_canon IS DISTINCT FROM f_this.attribute_canon
                AND 1 - (f_other.embedding <=> f_this.embedding) > %s
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
        return row


def get_relations(relation_type: str | None = None, document_id: str | None = None) -> list[dict]:
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
        WHERE (%s IS NULL OR r.relation = %s)
          AND (%s IS NULL OR fa.document_id = %s::uuid OR fb.document_id = %s::uuid)
        ORDER BY r.created_at DESC
    """
    with pool.connection() as conn:
        return conn.execute(
            query,
            (relation_type, relation_type, document_id, document_id, document_id),
        ).fetchall()


def get_fact_with_relations(fact_id: str) -> dict | None:
    with pool.connection() as conn:
        # Base fact with chunk + doc details
        fact = conn.execute(
            """SELECT f.*, c.page, c.bbox, d.filename AS document_filename
               FROM facts f
               JOIN documents d ON f.document_id = d.id
               LEFT JOIN chunks c ON f.chunk_id = c.id
               WHERE f.id = %s""",
            (str(fact_id),),
        ).fetchone()

        if not fact:
            return None

        # Relations with counterpart details
        rel_rows = conn.execute(
            """SELECT r.id AS relation_id, r.relation, r.explanation, r.rules_applied, r.confidence, r.created_at,
                      cf.id AS counterpart_id, cf.entity_canon, cf.attribute_canon, cf.raw_value, cf.norm_value,
                      cf.currency, cf.period, cf.scope, cf.quote,
                      cc.page, cc.bbox, cd.filename AS document_filename
               FROM fact_relations r
               JOIN facts cf ON (CASE WHEN r.fact_a = %s::uuid THEN r.fact_b ELSE r.fact_a END) = cf.id
               JOIN documents cd ON cf.document_id = cd.id
               LEFT JOIN chunks cc ON cf.chunk_id = cc.id
               WHERE r.fact_a = %s::uuid OR r.fact_b = %s::uuid
               ORDER BY r.created_at DESC""",
            (str(fact_id), str(fact_id), str(fact_id)),
        ).fetchall()

        fact_dict = dict(fact)
        fact_dict["relations"] = rel_rows
        return fact_dict


# ── matrix & fact search ─────────────────────────────────────────────

def get_matrix_data() -> dict:
    """Returns {entities: [...], attributes: [...], cells: {entity|attribute: [fact_ids]}, cell_badges: {...}}."""
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
    limit: int = 20,
) -> list[dict]:
    import json
    with pool.connection() as conn:
        if query_vector:
            emb_str = json.dumps(query_vector)
            sql = """
                SELECT f.*, c.page, c.bbox, d.filename,
                       COALESCE((
                           SELECT ARRAY_AGG(DISTINCT r.relation)
                           FROM fact_relations r
                           WHERE r.fact_a = f.id OR r.fact_b = f.id
                       ), ARRAY[]::text[]) AS relations_summary
                FROM facts f
                JOIN documents d ON f.document_id = d.id
                LEFT JOIN chunks c ON f.chunk_id = c.id
                WHERE (%s IS NULL OR f.document_id = %s::uuid)
                  AND (%s IS NULL OR f.entity_canon = %s)
                  AND (%s IS NULL OR f.attribute_canon = %s)
                  AND f.embedding IS NOT NULL
                ORDER BY f.embedding <=> %s::vector ASC
                LIMIT %s
            """
            rows = conn.execute(
                sql,
                (document_id, document_id, entity_canon, entity_canon, attribute_canon, attribute_canon, emb_str, limit),
            ).fetchall()
        else:
            sql = """
                SELECT f.*, c.page, c.bbox, d.filename,
                       COALESCE((
                           SELECT ARRAY_AGG(DISTINCT r.relation)
                           FROM fact_relations r
                           WHERE r.fact_a = f.id OR r.fact_b = f.id
                       ), ARRAY[]::text[]) AS relations_summary
                FROM facts f
                JOIN documents d ON f.document_id = d.id
                LEFT JOIN chunks c ON f.chunk_id = c.id
                WHERE (%s IS NULL OR f.document_id = %s::uuid)
                  AND (%s IS NULL OR f.entity_canon = %s)
                  AND (%s IS NULL OR f.attribute_canon = %s)
                ORDER BY f.created_at DESC
                LIMIT %s
            """
            rows = conn.execute(
                sql,
                (document_id, document_id, entity_canon, entity_canon, attribute_canon, attribute_canon, limit),
            ).fetchall()

        return [dict(r) for r in rows]


def search_facts_keyword(tokens: list[str], limit: int = 5) -> list[dict]:
    if not tokens:
        return []
    with pool.connection() as conn:
        clauses = []
        params: list[str] = []
        for t in tokens:
            pat = f"%{t}%"
            clauses.append("(f.entity ILIKE %s OR f.attribute ILIKE %s OR f.entity_canon ILIKE %s OR f.attribute_canon ILIKE %s)")
            params.extend([pat, pat, pat, pat])

        where_clause = " OR ".join(clauses)
        sql = f"""
            SELECT f.*, c.page, c.bbox, d.filename,
                   COALESCE((
                       SELECT ARRAY_AGG(DISTINCT r.relation)
                       FROM fact_relations r
                       WHERE r.fact_a = f.id OR r.fact_b = f.id
                   ), ARRAY[]::text[]) AS relations_summary
            FROM facts f
            JOIN documents d ON f.document_id = d.id
            LEFT JOIN chunks c ON f.chunk_id = c.id
            WHERE {where_clause}
            ORDER BY f.confidence DESC
            LIMIT %s
        """
        params.append(limit)
        rows = conn.execute(sql, tuple(params)).fetchall()
        return [dict(r) for r in rows]


def get_fact_lineage_audit(fact_id: str) -> list[dict]:
    """Retrieve ordered audit lineage for a given fact: ocr row (if any), extract row, reconcile rows."""
    with pool.connection() as conn:
        fact = conn.execute(
            """SELECT f.id, f.document_id, f.chunk_id, c.page
               FROM facts f
               LEFT JOIN chunks c ON f.chunk_id = c.id
               WHERE f.id = %s""",
            (str(fact_id),),
        ).fetchone()

        if not fact:
            return []

        doc_id = str(fact["document_id"])
        chunk_id = str(fact["chunk_id"]) if fact["chunk_id"] else None
        page = fact.get("page")

        # 1. OCR row (if any)
        ocr_rows = []
        if page is not None:
            ocr_rows = conn.execute(
                """SELECT * FROM audit
                   WHERE action LIKE 'ocr%%'
                     AND ((target->>'document_id' = %s AND (target->>'page')::int = %s)
                          OR ((meta->>'page')::int = %s AND (target->>'document_id' = %s OR meta->>'document_id' = %s)))
                   ORDER BY at ASC LIMIT 1""",
                (doc_id, page, page, doc_id, doc_id),
            ).fetchall()

        # 2. Extract row for this chunk/fact
        extract_rows = []
        if chunk_id:
            extract_rows = conn.execute(
                """SELECT * FROM audit
                   WHERE (action LIKE '%%extract%%' OR action = 'extract')
                     AND (target->>'chunk_id' = %s OR meta->>'chunk_id' = %s)
                   ORDER BY at ASC LIMIT 1""",
                (chunk_id, chunk_id),
            ).fetchall()

        # 3. Reconcile rows involving this fact
        reconcile_rows = conn.execute(
            """SELECT * FROM audit
               WHERE action = 'reconcile'
                 AND (target->>'fact_id' = %s
                      OR (meta->'pair_ids' ? %s)
                      OR (meta::text ILIKE %s))
               ORDER BY at ASC""",
            (str(fact_id), str(fact_id), f"%{fact_id}%"),
        ).fetchall()

        # Combined ordered lineage
        all_rows = list(ocr_rows) + list(extract_rows) + list(reconcile_rows)
        if not all_rows:
            all_rows = conn.execute(
                """SELECT * FROM audit
                   WHERE (target->>'fact_id' = %s)
                      OR (target->>'chunk_id' = %s)
                      OR (meta::text ILIKE %s)
                   ORDER BY at ASC""",
                (str(fact_id), chunk_id, f"%{fact_id}%"),
            ).fetchall()

        return [dict(r) for r in all_rows]


def audit(action: str, target: dict | None = None, meta: dict | None = None, actor: str = "system"):
    with pool.connection() as conn:
        conn.execute(
            """INSERT INTO audit (actor, action, target, meta)
               VALUES (%s, %s, %s::jsonb, %s::jsonb)""",
            (actor, action, psycopg.types.json.Json(target), psycopg.types.json.Json(meta)),
        )
