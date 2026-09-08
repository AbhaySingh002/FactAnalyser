"use client";

import { useState, useEffect, useRef } from "react";
import { api } from "@/lib/api";
import { Job, JobStage } from "@/lib/types";
import { toast } from "sonner";

export const STAGE_PROGRESS: Record<JobStage, number> = {
  queued: 5,
  parse: 20,
  route: 32,
  ocr: 45,
  chunk: 58,
  extract: 72,
  normalize: 84,
  embed: 92,
  reconcile: 97,
  done: 100,
  failed: 100,
};

export const STAGE_LABELS: Record<JobStage, string> = {
  queued: "Queued",
  parse: "Parsing Layout",
  route: "Routing Chunks",
  ocr: "Vision OCR",
  chunk: "Chunk Processing",
  extract: "Extracting Claims",
  normalize: "Normalizing Units",
  embed: "Embedding Facts",
  reconcile: "Cross-Doc Reconciliation",
  done: "Reconciled & Ready",
  failed: "Processing Failed",
};

interface UseJobOptions {
  onDone?: (job: Job) => void;
  onError?: (error: string) => void;
  showToasts?: boolean;
}

export function useJob(jobId: string | null | undefined, options?: UseJobOptions) {
  const [job, setJob] = useState<Job | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const prevStatusRef = useRef<string | null>(null);
  const optionsRef = useRef(options);
  optionsRef.current = options;

  useEffect(() => {
    if (!jobId) {
      setJob(null);
      setError(null);
      return;
    }

    let isMounted = true;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const poll = async () => {
      try {
        const j = await api.getJob(jobId);
        if (!isMounted) return;

        setJob(j);
        setError(null);

        // Check for state transitions
        if (prevStatusRef.current !== j.status) {
          if (j.status === "done") {
            if (optionsRef.current?.showToasts !== false) {
              toast.success("Document pipeline completed successfully", {
                description: `Document facts reconciled across knowledge layer.`,
              });
            }
            optionsRef.current?.onDone?.(j);
          } else if (j.status === "failed") {
            const errMsg = j.error || "Document processing failed";
            if (optionsRef.current?.showToasts !== false) {
              toast.error("Pipeline Failed", {
                description: errMsg,
              });
            }
            optionsRef.current?.onError?.(errMsg);
          }
          prevStatusRef.current = j.status;
        }

        if (j.status !== "done" && j.status !== "failed") {
          timer = setTimeout(poll, 2000);
        }
      } catch (err: any) {
        if (!isMounted) return;
        const msg = err?.message || "Failed to fetch job status";
        setError(msg);
        // Continue polling even on intermittent network glitches
        timer = setTimeout(poll, 3000);
      } finally {
        if (isMounted) setLoading(false);
      }
    };

    setLoading(true);
    poll();

    return () => {
      isMounted = false;
      if (timer) clearTimeout(timer);
    };
  }, [jobId]);

  const progress = job ? STAGE_PROGRESS[job.stage] ?? 0 : 0;
  const label = job ? STAGE_LABELS[job.stage] ?? job.stage : "Idle";

  return {
    job,
    loading,
    error,
    progress,
    label,
    isDone: job?.status === "done",
    isFailed: job?.status === "failed",
    isRunning: job?.status === "running" || job?.status === "pending",
  };
}
