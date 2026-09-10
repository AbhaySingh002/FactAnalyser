import {
  DocumentItem,
  Job,
  Fact,
  RelationRow,
  AuditRow,
  ChatResponse,
  UploadResponse,
  ReviewItem,
  ReviewStats,
  ReviewStatus,
  Citation,
  Finding,
  FindingsSummary,
  FindingStatus,
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
    history: { role: string; content: string }[] = [],
    options?: { deepResearch?: boolean; webSearch?: boolean }
  ): Promise<ChatResponse> {
    return fetchJson<ChatResponse>("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        history,
        deep_research: options?.deepResearch ?? true,
        web_search: options?.webSearch ?? true,
      }),
    });
  },

  async getReviewQueue(status: string = "pending", limit: number = 50): Promise<ReviewItem[]> {
    const sp = new URLSearchParams();
    if (status) sp.set("status", status);
    if (limit) sp.set("limit", String(limit));
    return fetchJson<ReviewItem[]>(`/review?${sp.toString()}`);
  },

  async getReviewStats(): Promise<ReviewStats> {
    return fetchJson<ReviewStats>("/review/stats");
  },

  async resolveReview(
    reviewId: string,
    status: ReviewStatus,
    reviewer: string = "auditor",
    decision: string = ""
  ): Promise<ReviewItem> {
    return fetchJson<ReviewItem>(`/review/${encodeURIComponent(reviewId)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status, reviewer, decision }),
    });
  },


  streamChat(
    message: string,
    history: { role: string; content: string }[],
    handlers: {
      onToken: (chunk: string) => void;
      onCitation?: (citations: Citation[]) => void;
      onStep?: (step: any) => void;
      onBlock?: (block: any) => void;
      onDone?: () => void;
      onError?: (err: Error) => void;
    },
    options?: {
      deepResearch?: boolean;
      webSearch?: boolean;
    }
  ): AbortController {
    const controller = new AbortController();

    (async () => {
      try {
        const url = `${API_BASE}/chat/stream`;
        const res = await fetch(url, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Accept: "text/event-stream",
          },
          body: JSON.stringify({
            message,
            history,
            deep_research: options?.deepResearch ?? true,
            web_search: options?.webSearch ?? true,
          }),
          signal: controller.signal,
        });

        if (!res.ok || !res.body) {
          // Fallback to static sendChat and stream simulated chunks
          const staticRes = await api.sendChat(message, history, options);
          const answer = staticRes.answer || "";
          const chunkSize = 24;
          for (let i = 0; i < answer.length; i += chunkSize) {
            if (controller.signal.aborted) return;
            handlers.onToken(answer.slice(i, i + chunkSize));
            await new Promise((r) => setTimeout(r, 20));
          }
          if (staticRes.citations?.length) {
            handlers.onCitation?.(staticRes.citations);
          }
          handlers.onDone?.();
          return;
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() || "";

          for (const line of lines) {
            const trimmed = line.trim();
            if (!trimmed.startsWith("data:")) continue;
            const dataStr = trimmed.slice(5).trim();
            if (!dataStr) continue;

            try {
              const parsed = JSON.parse(dataStr);
              if (parsed.type === "step" && parsed.step) {
                handlers.onStep?.(parsed.step);
              } else if (parsed.type === "block" && parsed.block) {
                handlers.onBlock?.(parsed.block);
              } else if (parsed.type === "text" && parsed.content) {
                handlers.onToken(parsed.content);
              } else if (parsed.type === "done") {
                if (parsed.citations && Array.isArray(parsed.citations)) {
                  handlers.onCitation?.(parsed.citations);
                }
                if (parsed.blocks && Array.isArray(parsed.blocks)) {
                  parsed.blocks.forEach((b: any) => handlers.onBlock?.(b));
                }
                handlers.onDone?.();
              }
            } catch {
              // Non-json or partial line - ignore
            }
          }
        }

        // Process leftover buffer
        if (buffer.trim().startsWith("data:")) {
          try {
            const parsed = JSON.parse(buffer.trim().slice(5).trim());
            if (parsed.type === "step" && parsed.step) {
              handlers.onStep?.(parsed.step);
            } else if (parsed.type === "block" && parsed.block) {
              handlers.onBlock?.(parsed.block);
            } else if (parsed.type === "text" && parsed.content) {
              handlers.onToken(parsed.content);
            } else if (parsed.type === "done") {
              if (parsed.citations) handlers.onCitation?.(parsed.citations);
              if (parsed.blocks) {
                parsed.blocks.forEach((b: any) => handlers.onBlock?.(b));
              }
            }
          } catch {
            // ignore
          }
        }

        handlers.onDone?.();
      } catch (err: any) {
        if (err.name === "AbortError") return;
        handlers.onError?.(err);
      }
    })();

    return controller;
  },

  async getFindings(params?: {
    category?: string;
    severity?: string;
    status?: string;
    document_id?: string;
    limit?: number;
  }): Promise<Finding[]> {
    const sp = new URLSearchParams();
    if (params?.category) sp.set("category", params.category);
    if (params?.severity) sp.set("severity", params.severity);
    if (params?.status) sp.set("status", params.status);
    if (params?.document_id) sp.set("document_id", params.document_id);
    if (params?.limit) sp.set("limit", String(params.limit));
    const qs = sp.toString() ? `?${sp.toString()}` : "";
    return fetchJson<Finding[]>(`/findings${qs}`);
  },

  async getFinding(findingId: string): Promise<Finding> {
    return fetchJson<Finding>(`/findings/${encodeURIComponent(findingId)}`);
  },

  async getFindingsSummary(): Promise<FindingsSummary> {
    return fetchJson<FindingsSummary>("/findings/summary");
  },

  async updateFindingStatus(
    findingId: string,
    status: FindingStatus
  ): Promise<Finding> {
    return fetchJson<Finding>(`/findings/${encodeURIComponent(findingId)}/status`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    });
  },

  async triggerAnalysis(document_ids?: string[]): Promise<{
    status: string;
    document_ids: string[] | null;
    message: string;
  }> {
    return fetchJson("/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ document_ids: document_ids || null }),
    });
  },
};
