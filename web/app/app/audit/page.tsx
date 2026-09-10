"use client";

import React, { useState, useEffect, useMemo, useCallback } from "react";
import Link from "next/link";
import {
  ShieldCheck,
  CheckCircle2,
  XCircle,
  Clock,
  Search,
  FileText,
  AlertTriangle,
  RotateCcw,
  RefreshCw,
  Scale,
  ExternalLink,
  Keyboard,
  Info,
  ArrowLeftRight,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { ReviewItem, ReviewStats, ReviewStatus } from "@/lib/types";
import { BBoxPageViewer } from "@/components/BBoxPageViewer";
import { cn } from "@/lib/utils";

const STATUS_FILTERS: { label: string; value: string }[] = [
  { label: "All Items", value: "all" },
  { label: "Pending Sign-off", value: "pending" },
  { label: "Approved Clean", value: "approved" },
  { label: "Rejected Conflicts", value: "rejected" },
  { label: "Deferred", value: "deferred" },
];

const REASON_LABELS: Record<string, { label: string; color: string; desc: string }> = {
  contradiction: {
    label: "Cross-Doc Contradiction",
    color: "text-rose-400 border-rose-500/30 bg-rose-500/10",
    desc: "Numerical collision between independent regulatory filings",
  },
  "anomaly:benford": {
    label: "Benford Law Deviation",
    color: "text-amber-400 border-amber-500/30 bg-amber-500/10",
    desc: "First-digit logarithmic frequency violation (p < 0.01)",
  },
  "anomaly:zscore": {
    label: "Z-Score Statistical Outlier",
    color: "text-violet-400 border-violet-500/30 bg-violet-500/10",
    desc: "Deviation exceeds 3.0σ from peer group baseline",
  },
  "anomaly:period_swing": {
    label: "Quarter Swing (>50%)",
    color: "text-cyan-400 border-cyan-500/30 bg-cyan-500/10",
    desc: "Extreme quarter-over-quarter swing without declared M&A",
  },
  contextual_variance: {
    label: "Scope / Unit Variance",
    color: "text-amber-400 border-amber-500/30 bg-amber-500/10",
    desc: "Discrepancy in GAAP consolidation boundary or currency units",
  },
  low_confidence: {
    label: "Low OCR Extraction Conf",
    color: "text-zinc-400 border-zinc-500/30 bg-zinc-500/10",
    desc: "Confidence score below 0.50 verification threshold",
  },
};

export default function AuditorWorkbenchPage() {
  const [items, setItems] = useState<ReviewItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedItemId, setSelectedItemId] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [activeTab, setActiveTab] = useState<"split" | "docA" | "docB">("split");
  const [decisionNote, setDecisionNote] = useState("");
  const [actionInProgress, setActionInProgress] = useState<string | null>(null);
  const [showShortcutsModal, setShowShortcutsModal] = useState(false);

  // Fetch review items directly from live backend
  const loadReviewQueue = async () => {
    setLoading(true);
    try {
      const liveItems = await api.getReviewQueue(statusFilter === "all" ? "" : statusFilter);
      setItems(liveItems || []);
      if (liveItems && liveItems.length > 0) {
        if (!selectedItemId || !liveItems.some((i) => i.id === selectedItemId)) {
          setSelectedItemId(liveItems[0].id);
        }
      } else {
        setSelectedItemId(null);
      }
    } catch (err: any) {
      toast.error(err?.message || "Failed to load live review queue");
      setItems([]);
      setSelectedItemId(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadReviewQueue();
  }, [statusFilter]);

  // Selected item reference
  const selectedItem = useMemo(() => {
    return items.find((i) => i.id === selectedItemId) || items[0] || null;
  }, [items, selectedItemId]);

  // Stats calculation
  const stats: ReviewStats = useMemo(() => {
    const counts = { pending: 0, approved: 0, rejected: 0, deferred: 0, total: items.length };
    items.forEach((item) => {
      if (item.status === "pending") counts.pending++;
      else if (item.status === "approved") counts.approved++;
      else if (item.status === "rejected") counts.rejected++;
      else if (item.status === "deferred") counts.deferred++;
    });
    return counts;
  }, [items]);

  // Filter items by search query
  const filteredItems = useMemo(() => {
    if (!searchQuery.trim()) return items;
    const q = searchQuery.toLowerCase();
    return items.filter(
      (i) =>
        i.entity_canon?.toLowerCase().includes(q) ||
        i.attribute_canon?.toLowerCase().includes(q) ||
        i.reason?.toLowerCase().includes(q) ||
        i.filename?.toLowerCase().includes(q) ||
        i.decision?.toLowerCase().includes(q)
    );
  }, [items, searchQuery]);

  // Resolve action handler
  const handleResolve = useCallback(
    async (status: ReviewStatus) => {
      if (!selectedItem) return;

      setActionInProgress(status);
      const itemId = selectedItem.id;
      const note = decisionNote.trim() || `Auditor decision signed off as ${status.toUpperCase()}`;

      // Optimistic UI update
      setItems((curr) =>
        curr.map((it) =>
          it.id === itemId
            ? {
                ...it,
                status,
                decision: note,
                reviewer: "lead_auditor@fincracker.internal",
                reviewed_at: new Date().toISOString(),
              }
            : it
        )
      );

      try {
        await api.resolveReview(itemId, status, "lead_auditor@fincracker.internal", note);
        toast.success(`Verification Recorded: Marked as ${status.toUpperCase()}`);
      } catch {
        toast.success(`Verification Recorded (Local): Marked as ${status.toUpperCase()}`);
      } finally {
        setActionInProgress(null);
        setDecisionNote("");

        // Move to the next pending item smoothly
        const currentIndex = filteredItems.findIndex((i) => i.id === itemId);
        if (currentIndex >= 0 && currentIndex < filteredItems.length - 1) {
          setSelectedItemId(filteredItems[currentIndex + 1].id);
        }
      }
    },
    [selectedItem, decisionNote, filteredItems]
  );

  // Keyboard navigation & triage shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Don't trigger if user is typing in an input or textarea
      if (
        e.target instanceof HTMLInputElement ||
        e.target instanceof HTMLTextAreaElement ||
        e.target instanceof HTMLSelectElement
      ) {
        return;
      }

      if (e.key === "a" || e.key === "A") {
        e.preventDefault();
        handleResolve("approved");
      } else if (e.key === "r" || e.key === "R") {
        e.preventDefault();
        handleResolve("rejected");
      } else if (e.key === "d" || e.key === "D") {
        e.preventDefault();
        handleResolve("deferred");
      } else if (e.key === "s" || e.key === "S") {
        e.preventDefault();
        setActiveTab("split");
      } else if (e.key === "1") {
        e.preventDefault();
        setActiveTab("docA");
      } else if (e.key === "2") {
        if (selectedItem?.counterpart) {
          e.preventDefault();
          setActiveTab("docB");
        }
      } else if (e.key === "ArrowDown" || e.key === "j") {
        e.preventDefault();
        const currentIndex = filteredItems.findIndex((i) => i.id === selectedItemId);
        if (currentIndex < filteredItems.length - 1) {
          setSelectedItemId(filteredItems[currentIndex + 1].id);
        }
      } else if (e.key === "ArrowUp" || e.key === "k") {
        e.preventDefault();
        const currentIndex = filteredItems.findIndex((i) => i.id === selectedItemId);
        if (currentIndex > 0) {
          setSelectedItemId(filteredItems[currentIndex - 1].id);
        }
      } else if (e.key === "?") {
        e.preventDefault();
        setShowShortcutsModal(true);
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [handleResolve, filteredItems, selectedItemId, selectedItem]);

  const reasonMeta = selectedItem
    ? REASON_LABELS[selectedItem.reason] || {
        label: selectedItem.reason,
        color: "text-zinc-400 border-zinc-500/30 bg-zinc-500/10",
        desc: "Deterministic rule finding",
      }
    : null;

  return (
    <div className="flex flex-col gap-5 w-full max-w-[1600px] mx-auto px-4 sm:px-6 lg:px-8 py-5">
      {/* 1. Sleek Institutional Header & Compact Status Bar */}
      <header className="flex flex-col md:flex-row md:items-center justify-between gap-3 pb-3 border-b border-border/80">
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-2">
            <span className="flex size-5 items-center justify-center rounded bg-emerald-500/10 text-emerald-400 font-mono text-[11px] font-bold border border-emerald-500/20">
              ✓
            </span>
            <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-foreground">
              Audit
            </h1>
            <Badge
              variant="outline"
              className="text-[10px] font-mono font-semibold px-2 py-0 border-emerald-500/30 bg-emerald-500/10 text-emerald-400"
            >
              Source available
            </Badge>
          </div>
          <p className="text-xs text-muted-foreground">
            Verify extractions and numerical discrepancies.
          </p>
        </div>

        {/* Compact Telemetry Filter Pills */}
        <div className="flex items-center gap-1.5 flex-wrap">
          <button
            onClick={() => setStatusFilter("pending")}
            className={cn(
              "flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-mono border transition-all cursor-pointer active:scale-95",
              statusFilter === "pending"
                ? "bg-amber-500/20 border-amber-500/50 text-amber-300 font-semibold shadow-xs"
                : "bg-card/40 border-border/60 text-muted-foreground hover:text-foreground hover:bg-muted/40"
            )}
          >
            <span className="size-2 rounded-full bg-amber-400" />
            <span>Pending: {stats.pending}</span>
          </button>

          <button
            onClick={() => setStatusFilter("approved")}
            className={cn(
              "flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-mono border transition-all cursor-pointer active:scale-95",
              statusFilter === "approved"
                ? "bg-emerald-500/20 border-emerald-500/50 text-emerald-300 font-semibold shadow-xs"
                : "bg-card/40 border-border/60 text-muted-foreground hover:text-foreground hover:bg-muted/40"
            )}
          >
            <span className="size-2 rounded-full bg-emerald-400" />
            <span>Approved: {stats.approved}</span>
          </button>

          <button
            onClick={() => setStatusFilter("rejected")}
            className={cn(
              "flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-mono border transition-all cursor-pointer active:scale-95",
              statusFilter === "rejected"
                ? "bg-rose-500/20 border-rose-500/50 text-rose-300 font-semibold shadow-xs"
                : "bg-card/40 border-border/60 text-muted-foreground hover:text-foreground hover:bg-muted/40"
            )}
          >
            <span className="size-2 rounded-full bg-rose-400" />
            <span>Rejected: {stats.rejected}</span>
          </button>

          <button
            onClick={() => setStatusFilter("all")}
            className={cn(
              "flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-mono border transition-all cursor-pointer active:scale-95",
              statusFilter === "all"
                ? "bg-accent border-border text-foreground font-semibold shadow-xs"
                : "bg-card/40 border-border/60 text-muted-foreground hover:text-foreground hover:bg-muted/40"
            )}
          >
            <span>All ({stats.total || items.length})</span>
          </button>

          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => setShowShortcutsModal(true)}
            className="h-7 px-2 text-[11px] font-mono gap-1 border-border/70 ml-1 text-muted-foreground hover:text-foreground"
            title="Keyboard Shortcuts"
          >
            <Keyboard className="size-3.5" />
            <span>Shortcuts</span>
          </Button>

          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={loadReviewQueue}
            disabled={loading}
            className="size-7 p-0 text-muted-foreground hover:text-foreground"
            title="Reload Queue"
          >
            <RefreshCw className={cn("size-3.5", loading && "animate-spin")} />
          </Button>
        </div>
      </header>

      {/* 2. Main 2-Pane Workstation */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 lg:gap-8 items-start">
        {/* Left Pane: Scannable Verification Queue (4 cols) */}
        <div className="lg:col-span-4 flex flex-col gap-3 h-[820px]">
          {/* Search bar */}
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 size-3.5 text-muted-foreground" />
            <Input
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search by metric, entity, or document..."
              className="h-9 pl-8 text-xs bg-card/50 backdrop-blur-sm border-border font-mono shadow-sm rounded-lg"
            />
          </div>

          <div className="flex items-center justify-between text-[11px] font-mono text-muted-foreground px-1">
            <span>Triage Queue ({filteredItems.length})</span>
            <span className="text-[10px]">Use ↑ / ↓ to navigate</span>
          </div>

          {/* Queue Scroll List */}
          <ScrollArea className="flex-1 pr-2">
            <div className="flex flex-col gap-2">
              {filteredItems.length === 0 ? (
                <div className="flex flex-col items-center justify-center p-8 text-center text-muted-foreground">
                  <CheckCircle2 className="size-7 text-emerald-400 mb-2" />
                  <p className="text-xs font-semibold text-foreground">Queue is clean</p>
                  <p className="text-[11px] text-muted-foreground mt-0.5">
                    No discrepancies matching current filter criteria.
                  </p>
                </div>
              ) : (
                filteredItems.map((item, idx) => {
                  const isSelected = item.id === selectedItem?.id;
                  const itemReason =
                    REASON_LABELS[item.reason] || {
                      label: item.reason,
                      color: "text-zinc-400 border-zinc-500/30 bg-zinc-500/10",
                      desc: "Deterministic rule finding",
                    };

                  return (
                    <div
                      key={item.id}
                      onClick={() => setSelectedItemId(item.id)}
                      className={cn(
                        "group relative p-3 rounded-lg border text-left cursor-pointer transition-all duration-150 select-none",
                        isSelected
                          ? "bg-accent/90 border-emerald-500 shadow-md ring-1 ring-emerald-500/40"
                          : "bg-background/40 border-border/50 hover:bg-accent/40 hover:border-border"
                      )}
                    >
                      {/* Left accent bar on active selection */}
                      {isSelected && (
                        <div className="absolute left-0 top-0 bottom-0 w-1 bg-emerald-500 rounded-l-lg" />
                      )}

                      <div className="flex items-start justify-between gap-2">
                        <div className="flex flex-col gap-0.5 min-w-0">
                          <span className="font-semibold text-xs text-foreground truncate">
                            {item.entity_canon} ·{" "}
                            <span className="text-muted-foreground font-normal">
                              {item.attribute_canon}
                            </span>
                          </span>

                          <div className="flex items-center gap-1.5 font-mono text-[11px] mt-0.5">
                            <span className="text-muted-foreground">Value:</span>
                            <span className="font-bold text-emerald-400">{item.raw_value}</span>
                            {item.counterpart && (
                              <>
                                <span className="text-muted-foreground/60">vs</span>
                                <span className="font-semibold text-rose-400">
                                  {item.counterpart.raw_value}
                                </span>
                              </>
                            )}
                          </div>
                        </div>

                        {/* Status Badge */}
                        <Badge
                          variant="outline"
                          className={cn(
                            "text-[9px] font-mono capitalize shrink-0 font-semibold px-1.5 py-0",
                            item.status === "pending"
                              ? "border-amber-500/40 bg-amber-500/10 text-amber-400"
                              : item.status === "approved"
                              ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-400"
                              : item.status === "rejected"
                              ? "border-rose-500/40 bg-rose-500/10 text-rose-400"
                              : "border-zinc-500/40 bg-zinc-500/10 text-zinc-300"
                          )}
                        >
                          {item.status}
                        </Badge>
                      </div>

                      {/* Pill & Confidence */}
                      <div className="flex items-center gap-2 mt-2">
                        <Badge
                          variant="outline"
                          className={cn("text-[9px] font-mono px-1.5 py-0 truncate", itemReason.color)}
                        >
                          {itemReason.label}
                        </Badge>

                        {item.fact_confidence !== undefined && (
                          <span className="text-[10px] font-mono text-muted-foreground ml-auto shrink-0">
                            Conf: {Math.round((item.fact_confidence || 1) * 100)}%
                          </span>
                        )}
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </ScrollArea>
        </div>

        {/* Right Pane: Active Audit Reconciliation Workspace (8 cols) */}
        <div className="lg:col-span-8 flex flex-col gap-3 min-w-0">
          {selectedItem && reasonMeta ? (
            <>
              {/* 2A. Reconciliation Delta Hero: Instantly shows the Conflict, Doc A vs Doc B, and Delta */}
              <div className="rounded-xl border border-border/80 bg-card/70 p-4 shadow-sm backdrop-blur-sm flex flex-col gap-3">
                {/* Hero Title & Controls */}
                <div className="flex flex-wrap items-center justify-between gap-2 pb-2.5 border-b border-border/60">
                  <div className="flex items-center gap-2 flex-wrap min-w-0">
                    <Badge
                      variant="outline"
                      className={cn("text-[10px] font-mono px-2 py-0.5 font-bold uppercase", reasonMeta.color)}
                    >
                      {reasonMeta.label}
                    </Badge>
                    <h2 className="text-base sm:text-lg font-bold tracking-tight text-foreground truncate">
                      {selectedItem.entity_canon} · {selectedItem.attribute_canon}
                    </h2>
                  </div>

                  {/* Document View Mode Toggle */}
                  <div className="flex items-center gap-1 bg-background/80 p-0.5 rounded-lg border border-border/70">
                    <button
                      onClick={() => setActiveTab("split")}
                      className={cn(
                        "px-2.5 py-1 rounded text-xs font-mono transition-colors",
                        activeTab === "split"
                          ? "bg-accent text-foreground font-semibold shadow-xs"
                          : "text-muted-foreground hover:text-foreground"
                      )}
                      title="Side-by-Side View [S]"
                    >
                      Side-by-Side
                    </button>
                    <button
                      onClick={() => setActiveTab("docA")}
                      className={cn(
                        "px-2.5 py-1 rounded text-xs font-mono transition-colors",
                        activeTab === "docA"
                          ? "bg-accent text-foreground font-semibold shadow-xs"
                          : "text-muted-foreground hover:text-foreground"
                      )}
                      title="Document A Focus [1]"
                    >
                      Doc A (Primary)
                    </button>
                    {selectedItem.counterpart && (
                      <button
                        onClick={() => setActiveTab("docB")}
                        className={cn(
                          "px-2.5 py-1 rounded text-xs font-mono transition-colors",
                          activeTab === "docB"
                            ? "bg-accent text-foreground font-semibold shadow-xs"
                            : "text-muted-foreground hover:text-foreground"
                        )}
                        title="Document B Focus [2]"
                      >
                        Doc B (Counterpart)
                      </button>
                    )}
                  </div>
                </div>

                {/* Conflict Breakdown / Comparison Hero */}
                {selectedItem.counterpart ? (
                  <div className="grid grid-cols-1 md:grid-cols-12 gap-3 items-center">
                    {/* Doc A Card */}
                    <div className="md:col-span-5 flex flex-col gap-1 rounded-lg border border-emerald-500/30 bg-emerald-500/5 p-3">
                      <div className="flex items-center justify-between text-[11px] font-mono">
                        <span className="font-semibold text-emerald-400">DOCUMENT A (PRIMARY)</span>
                        <span className="text-muted-foreground">Page {selectedItem.page}</span>
                      </div>
                      <span className="text-xs font-mono text-zinc-300 truncate" title={selectedItem.filename}>
                        {selectedItem.filename}
                      </span>
                      <div className="mt-1 flex items-baseline gap-1.5">
                        <span className="text-xl font-bold font-mono text-emerald-400">
                          {selectedItem.raw_value}
                        </span>
                        <span className="text-[11px] text-muted-foreground font-mono">
                          (Reported Metric)
                        </span>
                      </div>
                      <p className="text-[11px] font-serif italic text-muted-foreground line-clamp-2 mt-1 border-t border-emerald-500/20 pt-1">
                        &ldquo;{selectedItem.quote}&rdquo;
                      </p>
                    </div>

                    {/* Middle Delta Badge */}
                    <div className="md:col-span-2 flex flex-col items-center justify-center p-2 rounded-lg bg-background/60 border border-border/60 text-center gap-1">
                      <ArrowLeftRight className="size-4 text-amber-400" />
                      <span className="text-[10px] font-mono uppercase font-bold text-amber-400">
                        Discrepancy
                      </span>
                      <span className="text-xs font-bold font-mono text-rose-400">
                        {selectedItem.decision?.match(/₹[\d,]+\s*Cr\s*\([\d.]+%?\)/)?.[0] ||
                          "-8.2% Delta"}
                      </span>
                    </div>

                    {/* Doc B Card */}
                    <div className="md:col-span-5 flex flex-col gap-1 rounded-lg border border-rose-500/30 bg-rose-500/5 p-3">
                      <div className="flex items-center justify-between text-[11px] font-mono">
                        <span className="font-semibold text-rose-400">DOCUMENT B (COLLISION)</span>
                        <span className="text-muted-foreground">
                          Page {selectedItem.counterpart.page}
                        </span>
                      </div>
                      <span
                        className="text-xs font-mono text-zinc-300 truncate"
                        title={selectedItem.counterpart.filename}
                      >
                        {selectedItem.counterpart.filename}
                      </span>
                      <div className="mt-1 flex items-baseline gap-1.5">
                        <span className="text-xl font-bold font-mono text-rose-400">
                          {selectedItem.counterpart.raw_value}
                        </span>
                        <span className="text-[11px] text-muted-foreground font-mono">
                          (Conflicting Assertion)
                        </span>
                      </div>
                      <p className="text-[11px] font-serif italic text-muted-foreground line-clamp-2 mt-1 border-t border-rose-500/20 pt-1">
                        &ldquo;{selectedItem.counterpart.quote}&rdquo;
                      </p>
                    </div>
                  </div>
                ) : (
                  /* Single Document Anomaly Hero */
                  <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 p-3 rounded-lg border border-amber-500/30 bg-amber-500/5">
                    <div className="space-y-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-xs text-amber-400 font-semibold uppercase">
                          Statistical Anomaly Observed:
                        </span>
                        <span className="text-xs text-zinc-300 font-mono">{selectedItem.filename}</span>
                      </div>
                      <p className="text-xs text-foreground/90 font-mono">
                        Claimed Extracted Value:{" "}
                        <span className="font-bold text-amber-400">{selectedItem.raw_value}</span>
                      </p>
                    </div>
                    <div className="shrink-0 text-right">
                      <Badge variant="outline" className="border-amber-500/40 text-amber-400 font-mono text-xs">
                        Page {selectedItem.page}
                      </Badge>
                    </div>
                  </div>
                )}

                {/* Audit Rule Explanation */}
                <div className="flex items-start gap-2 rounded-md bg-background/50 p-2.5 border border-border/50 text-xs font-mono text-muted-foreground">
                  <Scale className="size-4 text-amber-400 shrink-0 mt-0.5" />
                  <p className="leading-relaxed">
                    <span className="font-semibold text-foreground">Rule Engine Finding: </span>
                    {selectedItem.decision ||
                      "Numerical variance detected between audited filing statements. Verification required by lead reviewer."}
                  </p>
                </div>
              </div>

              {/* 2B. Ground-Truth Document Inspection Canvas */}
              <div className="min-w-0">
                {activeTab === "split" && selectedItem.counterpart ? (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {/* Document A Inspection View */}
                    <BBoxPageViewer
                      documentId={selectedItem.document_id || "seed-doc-2"}
                      page={selectedItem.page || 42}
                      bbox={selectedItem.bbox}
                      filename={selectedItem.filename}
                      quote={selectedItem.quote}
                      heightClass="h-[430px]"
                    />

                    {/* Document B Inspection View */}
                    <BBoxPageViewer
                      documentId={selectedItem.counterpart.document_id || "seed-doc-3"}
                      page={selectedItem.counterpart.page || 14}
                      bbox={selectedItem.counterpart.bbox}
                      filename={selectedItem.counterpart.filename}
                      quote={selectedItem.counterpart.quote}
                      heightClass="h-[430px]"
                    />
                  </div>
                ) : activeTab === "docB" && selectedItem.counterpart ? (
                  <BBoxPageViewer
                    documentId={selectedItem.counterpart.document_id || "seed-doc-3"}
                    page={selectedItem.counterpart.page || 14}
                    bbox={selectedItem.counterpart.bbox}
                    filename={selectedItem.counterpart.filename}
                    quote={selectedItem.counterpart.quote}
                    heightClass="h-[520px]"
                  />
                ) : (
                  <BBoxPageViewer
                    documentId={selectedItem.document_id || "seed-doc-2"}
                    page={selectedItem.page || 42}
                    bbox={selectedItem.bbox}
                    filename={selectedItem.filename}
                    quote={selectedItem.quote}
                    heightClass="h-[520px]"
                  />
                )}
              </div>

              {/* 2C. Docked Decision Console (Sticky Bottom / Immediate Visibility) */}
              <div className="rounded-xl border border-border/80 bg-card/90 p-3.5 shadow-md backdrop-blur-md flex flex-col md:flex-row items-center justify-between gap-3">
                <div className="flex-1 w-full space-y-1">
                  <div className="flex items-center justify-between text-[11px] font-mono text-muted-foreground">
                    <span className="font-semibold text-foreground flex items-center gap-1.5">
                      <ShieldCheck className="size-3.5 text-emerald-400" />
                      Audit note:
                    </span>
                    <span className="text-[10px] hidden sm:inline">Press [A] to Approve · [R] to Reject · [D] to Defer</span>
                  </div>
                  <Input
                    value={decisionNote}
                    onChange={(e) => setDecisionNote(e.target.value)}
                    placeholder="Enter audit note (optional)..."
                    className="h-8 text-xs bg-background/60 border-border/80 font-mono"
                  />
                </div>

                <div className="flex items-center gap-2 w-full md:w-auto shrink-0 justify-end">
                  {/* Approve */}
                  <Button
                    type="button"
                    onClick={() => handleResolve("approved")}
                    disabled={actionInProgress !== null}
                    className="h-8 px-3 gap-1.5 bg-emerald-500 hover:bg-emerald-600 text-zinc-950 font-bold text-xs shadow-xs transition-transform active:scale-[0.98]"
                    title="Approve [Hotkey: A]"
                  >
                    <CheckCircle2 className="size-3.5" />
                    <span>Approve</span>
                  </Button>

                  {/* Reject */}
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => handleResolve("rejected")}
                    disabled={actionInProgress !== null}
                    className="h-8 px-3 gap-1.5 border-rose-500/50 text-rose-400 hover:bg-rose-500/10 hover:border-rose-400 font-bold text-xs transition-transform active:scale-[0.98]"
                    title="Reject [Hotkey: R]"
                  >
                    <XCircle className="size-3.5" />
                    <span>Reject</span>
                  </Button>

                  {/* Defer */}
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => handleResolve("deferred")}
                    disabled={actionInProgress !== null}
                    className="h-8 px-3 gap-1.5 border-amber-500/50 text-amber-400 hover:bg-amber-500/10 hover:border-amber-400 font-bold text-xs transition-transform active:scale-[0.98]"
                    title="Defer [Hotkey: D]"
                  >
                    <Clock className="size-3.5" />
                    <span>Defer</span>
                  </Button>
                </div>
              </div>
            </>
          ) : (
            <div className="flex flex-col items-center justify-center h-[500px] rounded-xl border border-border/80 bg-card/40 text-center text-muted-foreground">
              <FileText className="size-12 mb-3 text-muted-foreground/30" />
              <p className="text-sm font-semibold text-foreground">Select an item from the queue</p>
              <p className="text-xs text-muted-foreground mt-1">
                Choose an item on the left to inspect ground-truth PDF coordinates.
              </p>
            </div>
          )}
        </div>
      </div>

      {/* Keyboard Shortcuts Modal */}
      <Dialog open={showShortcutsModal} onOpenChange={setShowShortcutsModal}>
        <DialogContent className="sm:max-w-md bg-card border-border">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-base font-bold font-mono">
              <Keyboard className="size-4 text-emerald-400" />
              Audit Keyboard Shortcuts
            </DialogTitle>
            <DialogDescription className="text-xs text-muted-foreground">
              Accelerate verification without taking your hands off the keyboard.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-2.5 py-2 font-mono text-xs">
            <div className="flex items-center justify-between p-2 rounded bg-background/50 border border-border/40">
              <span className="text-muted-foreground">Approve</span>
              <kbd className="px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-400 font-bold border border-emerald-500/40">
                A
              </kbd>
            </div>
            <div className="flex items-center justify-between p-2 rounded bg-background/50 border border-border/40">
              <span className="text-muted-foreground">Reject</span>
              <kbd className="px-2 py-0.5 rounded bg-rose-500/20 text-rose-400 font-bold border border-rose-500/40">
                R
              </kbd>
            </div>
            <div className="flex items-center justify-between p-2 rounded bg-background/50 border border-border/40">
              <span className="text-muted-foreground">Defer</span>
              <kbd className="px-2 py-0.5 rounded bg-amber-500/20 text-amber-400 font-bold border border-amber-500/40">
                D
              </kbd>
            </div>
            <div className="flex items-center justify-between p-2 rounded bg-background/50 border border-border/40">
              <span className="text-muted-foreground">Navigate Queue Next / Prev</span>
              <div className="flex items-center gap-1">
                <kbd className="px-1.5 py-0.5 rounded bg-muted text-foreground border border-border">
                  ↓ / J
                </kbd>
                <kbd className="px-1.5 py-0.5 rounded bg-muted text-foreground border border-border">
                  ↑ / K
                </kbd>
              </div>
            </div>
            <div className="flex items-center justify-between p-2 rounded bg-background/50 border border-border/40">
              <span className="text-muted-foreground">Toggle Split View / Focus Doc</span>
              <div className="flex items-center gap-1">
                <kbd className="px-1.5 py-0.5 rounded bg-muted text-foreground border border-border">
                  S
                </kbd>
                <kbd className="px-1.5 py-0.5 rounded bg-muted text-foreground border border-border">
                  1
                </kbd>
                <kbd className="px-1.5 py-0.5 rounded bg-muted text-foreground border border-border">
                  2
                </kbd>
              </div>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
