export type RelationType =
  | "corroborates"
  | "contradicts"
  | "contextual_variance"
  | "needs_review";

export interface DocumentItem {
  id: string;
  filename: string;
  sha256: string;
  created_at: string;
  page_count: number;
  r2_key?: string;
}

export type JobStage =
  | "queued"
  | "parse"
  | "route"
  | "ocr"
  | "chunk"
  | "extract"
  | "normalize"
  | "embed"
  | "reconcile"
  | "done"
  | "failed";

export type JobStatus = "pending" | "running" | "done" | "failed";

export interface Job {
  id: string;
  document_id: string;
  stage: JobStage;
  status: JobStatus;
  error?: string | null;
  created_at: string;
  updated_at: string;
}

export interface FactRelation {
  relation_id: string;
  relation: RelationType;
  explanation: string;
  rules_applied: string[];
  confidence: number;
  created_at?: string;
  counterpart_id: string;
  entity_canon?: string;
  attribute_canon?: string;
  raw_value?: string;
  norm_value?: number | null;
  currency?: string | null;
  period?: string | null;
  scope?: string | null;
  quote?: string;
  page?: number;
  bbox?: [number, number, number, number];
  document_filename?: string;
}

export interface Fact {
  id: string;
  document_id: string;
  chunk_id?: string | null;
  entity: string;
  attribute: string;
  entity_canon: string;
  attribute_canon: string;
  raw_value: string;
  norm_value?: number | null;
  norm_unit?: string | null;
  currency?: string | null;
  period?: string | null;
  scope?: string | null;
  quote: string;
  confidence: number;
  model: string;
  prompt_ver: string;
  created_at?: string;
  page?: number;
  bbox?: [number, number, number, number];
  document_filename?: string;
  relations?: FactRelation[];
}

export interface CellDetail {
  fact_ids: string[];
  badge: RelationType | null;
}

export interface MatrixData {
  entities: string[];
  attributes: string[];
  cells: Record<string, CellDetail>;
  cell_facts: Record<string, string[]>;
  cell_badges: Record<string, RelationType | null>;
}

export interface RelationRow {
  id: string;
  a_id: string;
  b_id: string;
  a_document_id: string;
  b_document_id: string;
  relation: RelationType;
  explanation: string;
  rules_applied: string[];
  confidence: number;
  created_at?: string;
}

export interface AuditRow {
  id: string;
  actor: string;
  action: string;
  target?: Record<string, unknown>;
  meta?: Record<string, unknown>;
  at: string;
}

export interface Citation {
  fact_id: string;
  page?: number;
  filename?: string;
  quote?: string;
}

export interface ChatResponse {
  answer: string;
  citations: Citation[];
}

export interface UploadResponse {
  document_id: string;
  job_id: string | null;
  dedupe?: boolean;
}
