"use client";

import React, { useState, useEffect, useRef } from "react";
import Link from "next/link";
import {
  UploadCloud,
  FileText,
  Table as TableIcon,
  CheckCircle2,
  AlertTriangle,
  RotateCcw,
  Loader2,
  Layers,
  ArrowRight,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { DocumentItem, Job } from "@/lib/types";
import { STAGE_PROGRESS, STAGE_LABELS } from "@/hooks/useJob";

export default function DashboardPage() {
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Upload state
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Active jobs map: documentId -> Job
  const [jobs, setJobs] = useState<Record<string, Job>>({});

  const loadDocuments = async () => {
    try {
      setLoading(true);
      const docs = await api.getDocuments();
      setDocuments(docs);
      setError(null);
    } catch (err: any) {
      setError(err?.message || "Failed to load documents");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadDocuments();
  }, []);

  // Poll running jobs every 2 seconds
  useEffect(() => {
    const activeDocIds = Object.keys(jobs).filter(
      (id) => jobs[id].status === "running" || jobs[id].status === "pending"
    );

    if (activeDocIds.length === 0) return;

    const interval = setInterval(async () => {
      for (const docId of activeDocIds) {
        const currentJob = jobs[docId];
        if (!currentJob?.id) continue;

        try {
          const updated = await api.getJob(currentJob.id);
          setJobs((prev) => ({ ...prev, [docId]: updated }));

          if (updated.status === "done") {
            toast.success("Document pipeline complete", {
              description: `Facts extracted and reconciled across knowledge layer.`,
            });
            loadDocuments();
          } else if (updated.status === "failed") {
            toast.error("Pipeline failed", {
              description: updated.error || "Unknown error during document processing.",
            });
          }
        } catch {
          // ignore transient poll error
        }
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [jobs]);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      if (!file.name.toLowerCase().endsWith(".pdf")) {
        toast.error("Invalid file format", {
          description: "Please upload a valid PDF document.",
        });
        return;
      }
      setUploadFile(file);
    }
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) {
      if (!file.name.toLowerCase().endsWith(".pdf")) {
        toast.error("Invalid file format", {
          description: "Please upload a valid PDF document.",
        });
        return;
      }
      setUploadFile(file);
    }
  };

  const handleUpload = async () => {
    if (!uploadFile) return;

    setIsUploading(true);
    const uploadToastId = toast.loading(`Uploading ${uploadFile.name}...`);

    try {
      const res = await api.uploadDocument(uploadFile);
      toast.dismiss(uploadToastId);

      if (res.dedupe) {
        toast.info("Document already indexed", {
          description: "This PDF content hash was already processed.",
        });
      } else {
        toast.success("File uploaded successfully", {
          description: "Pipeline queued: parsing layout and extracting claims.",
        });
      }

      setUploadFile(null);
      if (fileInputRef.current) fileInputRef.current.value = "";

      // Refresh documents
      await loadDocuments();

      // If a job was returned, track it
      if (res.job_id) {
        const initialJob: Job = {
          id: res.job_id,
          document_id: res.document_id,
          stage: "queued",
          status: "pending",
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        };
        setJobs((prev) => ({ ...prev, [res.document_id]: initialJob }));
      }
    } catch (err: any) {
      toast.dismiss(uploadToastId);
      toast.error("Upload failed", {
        description: err?.message || "Could not upload document.",
      });
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-border/60 pb-5">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">
            Document Repository
          </h1>
          <p className="text-xs sm:text-sm text-muted-foreground mt-0.5">
            Ingest financial reports, filings, and contracts for provenance extraction and cross-reconciliation.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Link href="/app/matrix">
            <Button className="h-9 px-3.5 text-xs bg-emerald-500 text-zinc-950 hover:bg-emerald-400 font-semibold shadow-xs">
              <TableIcon className="size-3.5 mr-1.5" />
              Open Matrix
              <ArrowRight className="size-3.5 ml-1" />
            </Button>
          </Link>
        </div>
      </div>

      {/* Upload Dropzone Card */}
      <Card className="border-border/70 bg-card/50 backdrop-blur">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-semibold flex items-center gap-2">
            <UploadCloud className="size-4 text-emerald-400" />
            Ingest Document (PDF)
          </CardTitle>
          <CardDescription className="text-xs">
            Documents undergo automated layout parsing, vision OCR fallback, structured claim extraction, and cross-reconciliation.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setIsDragging(true);
            }}
            onDragLeave={() => setIsDragging(false)}
            onDrop={handleDrop}
            className={`flex flex-col items-center justify-center rounded-lg border-2 border-dashed p-6 text-center transition-colors ${
              isDragging
                ? "border-emerald-500 bg-emerald-500/5"
                : "border-border/80 hover:border-border"
            }`}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,application/pdf"
              onChange={handleFileChange}
              className="hidden"
              id="pdf-upload"
            />

            <UploadCloud className="size-8 text-muted-foreground/80 mb-2" />

            {uploadFile ? (
              <div className="space-y-3">
                <div className="flex items-center gap-2 rounded bg-muted/50 px-3 py-1.5 font-mono text-xs text-foreground border border-border/60">
                  <FileText className="size-4 text-emerald-400" />
                  <span className="font-medium">{uploadFile.name}</span>
                  <span className="text-muted-foreground">
                    ({(uploadFile.size / 1024 / 1024).toFixed(2)} MB)
                  </span>
                </div>

                <div className="flex items-center justify-center gap-2">
                  <Button
                    size="sm"
                    onClick={handleUpload}
                    disabled={isUploading}
                    className="h-8 px-3 text-xs bg-emerald-500 text-zinc-950 hover:bg-emerald-400 font-medium"
                  >
                    {isUploading ? (
                      <>
                        <Loader2 className="size-3.5 animate-spin mr-1.5" />
                        Processing...
                      </>
                    ) : (
                      "Start Ingestion Pipeline"
                    )}
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => {
                      setUploadFile(null);
                      if (fileInputRef.current) fileInputRef.current.value = "";
                    }}
                    disabled={isUploading}
                    className="h-8 text-xs text-muted-foreground"
                  >
                    Cancel
                  </Button>
                </div>
              </div>
            ) : (
              <div className="space-y-1.5">
                <label
                  htmlFor="pdf-upload"
                  className="cursor-pointer text-xs font-semibold text-emerald-400 hover:text-emerald-300 underline underline-offset-4"
                >
                  Click to select a PDF
                </label>
                <span className="text-xs text-muted-foreground"> or drag and drop filing here</span>
                <p className="text-[11px] text-muted-foreground/80 font-mono">
                  Standard 10-K, 10-Q, pitch decks, audited financial statements (Max 50MB)
                </p>
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Documents Table */}
      <Card className="border-border/70 bg-card/50">
        <CardHeader className="pb-3 flex flex-row items-center justify-between border-b border-border/60">
          <div>
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <Layers className="size-4 text-emerald-400" />
              Ingested Documents ({documents.length})
            </CardTitle>
            <CardDescription className="text-xs mt-0.5">
              Live status and pipeline progress across knowledge base documents.
            </CardDescription>
          </div>

          <Button
            variant="ghost"
            size="sm"
            onClick={loadDocuments}
            disabled={loading}
            className="h-8 px-2 text-xs text-muted-foreground hover:text-foreground"
          >
            <RotateCcw className={`size-3.5 mr-1 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </Button>
        </CardHeader>

        <CardContent className="p-0">
          {loading && documents.length === 0 ? (
            <div className="p-6 space-y-3">
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
            </div>
          ) : error ? (
            <div className="p-8 text-center space-y-2">
              <AlertTriangle className="size-6 text-rose-400 mx-auto" />
              <p className="text-sm font-medium">{error}</p>
              <Button size="sm" variant="outline" onClick={loadDocuments}>
                Retry
              </Button>
            </div>
          ) : documents.length === 0 ? (
            <div className="p-12 text-center space-y-3">
              <FileText className="size-8 text-muted-foreground mx-auto opacity-60" />
              <div className="space-y-1">
                <p className="text-sm font-semibold text-foreground">No documents uploaded yet</p>
                <p className="text-xs text-muted-foreground max-w-sm mx-auto">
                  Upload your first financial or legal PDF above to start extracting grounded facts and identifying cross-document discrepancies.
                </p>
              </div>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow className="border-border/60 hover:bg-transparent">
                  <TableHead className="w-[300px] text-xs font-semibold">Document Name</TableHead>
                  <TableHead className="w-[80px] text-xs font-semibold">Pages</TableHead>
                  <TableHead className="w-[220px] text-xs font-semibold">Pipeline Stage</TableHead>
                  <TableHead className="text-xs font-semibold">Status</TableHead>
                  <TableHead className="text-xs font-semibold">Ingested At</TableHead>
                  <TableHead className="text-right text-xs font-semibold">Action</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {documents.map((doc) => {
                  const activeJob = jobs[doc.id];
                  const stage = activeJob?.stage;
                  const isJobActive =
                    activeJob &&
                    (activeJob.status === "running" || activeJob.status === "pending");
                  const progressVal = stage ? STAGE_PROGRESS[stage] ?? 100 : 100;
                  const stageLabel = stage ? STAGE_LABELS[stage] ?? stage : "Indexed";

                  return (
                    <TableRow key={doc.id} className="border-border/60 hover:bg-muted/30">
                      <TableCell className="font-medium text-xs">
                        <div className="flex items-center gap-2">
                          <FileText className="size-4 text-emerald-400 shrink-0" />
                          <div className="flex flex-col truncate">
                            <span className="truncate font-semibold text-foreground" title={doc.filename}>
                              {doc.filename}
                            </span>
                            <span className="font-mono text-[10px] text-muted-foreground truncate">
                              SHA: {doc.sha256.slice(0, 12)}...
                            </span>
                          </div>
                        </div>
                      </TableCell>

                      <TableCell className="font-mono text-xs text-muted-foreground">
                        {doc.page_count ? `${doc.page_count} pp` : "—"}
                      </TableCell>

                      <TableCell className="text-xs">
                        {isJobActive ? (
                          <div className="space-y-1.5 w-full max-w-[180px]">
                            <div className="flex items-center justify-between text-[10px] font-mono">
                              <span className="text-emerald-400 animate-pulse font-medium">
                                {stageLabel}
                              </span>
                              <span className="text-muted-foreground">{progressVal}%</span>
                            </div>
                            <Progress value={progressVal} className="h-1.5 bg-muted" />
                          </div>
                        ) : activeJob?.status === "failed" ? (
                          <span className="font-mono text-[11px] text-rose-400">
                            Failed: {activeJob.error || "Execution error"}
                          </span>
                        ) : (
                          <span className="font-mono text-[11px] text-muted-foreground flex items-center gap-1.5">
                            <CheckCircle2 className="size-3 text-emerald-400" />
                            Fully Indexed
                          </span>
                        )}
                      </TableCell>

                      <TableCell>
                        {isJobActive ? (
                          <Badge
                            variant="outline"
                            className="bg-amber-500/10 text-amber-400 border-amber-500/30 text-[10px] font-mono"
                          >
                            Processing
                          </Badge>
                        ) : activeJob?.status === "failed" ? (
                          <Badge
                            variant="outline"
                            className="bg-rose-500/10 text-rose-400 border-rose-500/30 text-[10px] font-mono"
                          >
                            Error
                          </Badge>
                        ) : (
                          <Badge
                            variant="outline"
                            className="bg-emerald-500/10 text-emerald-400 border-emerald-500/30 text-[10px] font-mono"
                          >
                            Ready
                          </Badge>
                        )}
                      </TableCell>

                      <TableCell className="font-mono text-[11px] text-muted-foreground">
                        {new Date(doc.created_at).toLocaleDateString()} ·{" "}
                        {new Date(doc.created_at).toLocaleTimeString([], {
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                      </TableCell>

                      <TableCell className="text-right">
                        <Link href={`/app/matrix?doc=${encodeURIComponent(doc.id)}`}>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-7 px-2 text-[11px] text-muted-foreground hover:text-foreground"
                          >
                            View Facts
                            <ArrowRight className="size-3 ml-1" />
                          </Button>
                        </Link>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
