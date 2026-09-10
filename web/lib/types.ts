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
  index?: number;
  fact_id: string;
  page?: number;
  filename?: string;
  quote?: string;
  entity?: string;
  attribute?: string;
  raw_value?: string;
  confidence?: number;
}

export interface ChatResponse {
  answer: string;
  citations: Citation[];
  blocks?: any[];
}

export interface UploadResponse {
  document_id: string;
  job_id: string | null;
  dedupe?: boolean;
}

export type ReviewStatus = "pending" | "approved" | "rejected" | "deferred";

export interface ReviewItem {
  id: string;
  fact_id?: string | null;
  relation_id?: string | null;
  reason: string; // 'anomaly:benford' | 'anomaly:zscore' | 'anomaly:period_swing' | 'contradiction' | 'low_confidence' etc.
  status: ReviewStatus;
  decision?: string;
  reviewer?: string;
  created_at?: string;
  reviewed_at?: string;
  // Joined fact & doc metadata
  entity_canon?: string;
  attribute_canon?: string;
  raw_value?: string;
  norm_value?: number | null;
  fact_confidence?: number;
  quote?: string;
  filename?: string;
  document_id?: string;
  page?: number;
  bbox?: [number, number, number, number];
  // Counterpart metadata for cross-document contradictions/variances
  counterpart?: {
    id: string;
    entity_canon?: string;
    attribute_canon?: string;
    raw_value?: string;
    norm_value?: number | null;
    quote?: string;
    filename?: string;
    document_id?: string;
    page?: number;
    bbox?: [number, number, number, number];
  };
}

export interface ReviewStats {
  pending: number;
  approved: number;
  rejected: number;
  deferred: number;
  total?: number;
}


export type FindingCategory =
  | "contradiction"
  | "anomaly"
  | "missing_disclosure"
  | "computational_error"
  | "contextual_variance";

export type FindingSeverity = "critical" | "high" | "medium" | "low" | "info";

export type FindingStatus = "open" | "confirmed" | "dismissed" | "resolved";

export interface Finding {
  id: string;
  case_id?: string | null;
  category: FindingCategory;
  severity: FindingSeverity;
  title: string;
  description: string;
  explanation?: string | null;
  fact_ids: string[];
  relation_ids: string[];
  evidence_ids: string[];
  document_ids: string[];
  details: Record<string, any>;
  status: FindingStatus;
  created_at: string;
  fact_details?: Array<{
    id: string;
    entity_canon?: string;
    attribute_canon?: string;
    raw_value?: string;
    norm_value?: number | null;
    period?: string;
    scope?: string;
    quote?: string;
    page?: number;
    filename?: string;
    confidence?: number;
  }>;
}

export interface FindingsSummary {
  total: number;
  by_severity: {
    critical: number;
    high: number;
    medium: number;
    low: number;
    info: number;
  };
  by_category: Record<string, number>;
  by_status: {
    open: number;
    confirmed: number;
    dismissed: number;
    resolved: number;
  };
}
