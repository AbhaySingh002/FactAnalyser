import {
  DocumentItem,
  Job,
  MatrixData,
  Fact,
  RelationRow,
  AuditRow,
  ChatResponse,
  UploadResponse,
} from "./types";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/+$/, "") || "http://localhost:8000";

async function fetchJson<T>(endpoint: string, init?: RequestInit): Promise<T> {
  const url = `${API_BASE}${endpoint.startsWith("/") ? endpoint : `/${endpoint}`}`;
  const res = await fetch(url, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(init?.headers || {}),
    },
  });

  if (!res.ok) {
    let errorDetail = res.statusText;
    try {
      const errJson = await res.json();
      errorDetail = errJson.error || errJson.detail || JSON.stringify(errJson);
    } catch {
      // ignore
    }
    throw new Error(`API Error (${res.status}): ${errorDetail}`);
  }

  return res.json();
}

export const api = {
  async health(): Promise<boolean> {
    try {
      const res = await fetch(`${API_BASE}/health`, { signal: AbortSignal.timeout(3000) });
      return res.ok;
    } catch {
      return false;
    }
  },

  async getDocuments(): Promise<DocumentItem[]> {
    return fetchJson<DocumentItem[]>("/documents");
  },

  async uploadDocument(file: File): Promise<UploadResponse> {
    const formData = new FormData();
    formData.append("file", file);
    return fetchJson<UploadResponse>("/documents", {
      method: "POST",
      body: formData,
    });
  },

  async getJob(jobId: string): Promise<Job> {
    return fetchJson<Job>(`/jobs/${encodeURIComponent(jobId)}`);
  },

  async getMatrix(): Promise<MatrixData> {
    return fetchJson<MatrixData>("/matrix");
  },

  async getFacts(params?: {
    document_id?: string;
    entity_canon?: string;
    attribute_canon?: string;
    q?: string;
    limit?: number;
  }): Promise<Fact[]> {
    const sp = new URLSearchParams();
    if (params?.document_id) sp.set("document_id", params.document_id);
    if (params?.entity_canon) sp.set("entity_canon", params.entity_canon);
    if (params?.attribute_canon) sp.set("attribute_canon", params.attribute_canon);
    if (params?.q) sp.set("q", params.q);
    if (params?.limit) sp.set("limit", String(params.limit));
    const qs = sp.toString() ? `?${sp.toString()}` : "";
    return fetchJson<Fact[]>(`/facts${qs}`);
  },

  async getFact(factId: string): Promise<Fact> {
    return fetchJson<Fact>(`/facts/${encodeURIComponent(factId)}`);
  },

  async getRelations(params?: {
    type?: string;
    document_id?: string;
  }): Promise<RelationRow[]> {
    const sp = new URLSearchParams();
    if (params?.type) sp.set("type", params.type);
    if (params?.document_id) sp.set("document_id", params.document_id);
    const qs = sp.toString() ? `?${sp.toString()}` : "";
    return fetchJson<RelationRow[]>(`/relations${qs}`);
  },

  getPageImageUrl(docId: string, page: number): string {
    return `${API_BASE}/pages/${encodeURIComponent(docId)}/${page}`;
  },

  async getAudit(factId?: string): Promise<AuditRow[]> {
    const qs = factId ? `?fact_id=${encodeURIComponent(factId)}` : "";
    return fetchJson<AuditRow[]>(`/audit${qs}`);
  },

  async sendChat(
    message: string,
    history: { role: string; content: string }[] = []
  ): Promise<ChatResponse> {
    return fetchJson<ChatResponse>("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, history }),
    });
  },
};
