"use client";

import React, { useState, useEffect } from "react";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertTitle, AlertDescription } from "@/components/ui/alert";
import {
  Accordion,
  AccordionItem,
  AccordionTrigger,
  AccordionContent,
} from "@/components/ui/accordion";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  FileCheck,
  Quote,
  Layers,
  History,
  AlertTriangle,
  RotateCcw,
  Sparkles,
  ExternalLink,
} from "lucide-react";
import { api } from "@/lib/api";
import { Fact, AuditRow } from "@/lib/types";
import { RelationBadge } from "./RelationBadge";
import { BBoxPageViewer } from "./BBoxPageViewer";

interface EvidenceSheetProps {
  factId: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSelectCounterpart?: (counterpartFactId: string) => void;
}

export function EvidenceSheet({
  factId,
  open,
  onOpenChange,
  onSelectCounterpart,
}: EvidenceSheetProps) {
  const [fact, setFact] = useState<Fact | null>(null);
  const [auditRows, setAuditRows] = useState<AuditRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchFactData = async (id: string) => {
    setLoading(true);
    setError(null);
    try {
      const [factData, auditData] = await Promise.all([
        api.getFact(id),
        api.getAudit(id).catch(() => []),
      ]);
      setFact(factData);
      setAuditRows(auditData);
    } catch (err: any) {
      setError(err?.message || "Failed to load fact evidence");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (open && factId) {
      fetchFactData(factId);
    } else if (!open) {
      setFact(null);
      setError(null);
    }
  }, [open, factId]);

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        className="w-full sm:max-w-2xl p-0 flex flex-col h-full bg-background border-l border-border/80"
      >
        <SheetHeader className="px-6 pt-5 pb-3 border-b border-border/60">
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <span className="flex size-6 items-center justify-center rounded bg-emerald-500/10 text-emerald-400">
                <FileCheck className="size-3.5" />
              </span>
              <SheetTitle className="text-base font-semibold tracking-tight">
                Grounding & Lineage Evidence
              </SheetTitle>
            </div>
            {fact && (
              <Badge
                variant="outline"
                className="font-mono text-[11px] bg-muted/30"
              >
                ID: {fact.id.slice(0, 8)}
              </Badge>
            )}
          </div>
          <SheetDescription className="text-xs text-muted-foreground mt-0.5">
            Cryptographic document provenance, bounding-box evidence, and cross-reconciliation history.
          </SheetDescription>
        </SheetHeader>

        <ScrollArea className="flex-1 px-6 py-4">
          {loading ? (
            <div className="space-y-4 py-2">
              <Skeleton className="h-8 w-3/4" />
              <Skeleton className="h-4 w-1/2" />
              <Skeleton className="h-24 w-full" />
              <Skeleton className="h-64 w-full" />
            </div>
          ) : error ? (
            <div className="py-12 text-center space-y-3">
              <AlertTriangle className="size-8 text-rose-400 mx-auto" />
              <p className="text-sm font-medium text-foreground">
                Unable to load evidence record
              </p>
              <p className="text-xs text-muted-foreground max-w-sm mx-auto">
                {error}
              </p>
              <Button
                variant="outline"
                size="sm"
                onClick={() => factId && fetchFactData(factId)}
                className="mt-2"
              >
                <RotateCcw className="size-3.5 mr-1.5" />
                Retry
              </Button>
            </div>
          ) : fact ? (
            <div className="space-y-5 pb-6">
              {/* Header: entity · attribute · value */}
              <div className="space-y-2 rounded-lg border border-border/70 bg-card/60 p-3.5">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
                    <span className="text-foreground font-semibold">
                      {fact.entity_canon || fact.entity}
                    </span>
                    <span>·</span>
                    <span className="font-mono text-zinc-300">
                      {fact.attribute_canon || fact.attribute}
                    </span>
                    {fact.period && (
                      <>
                        <span>·</span>
                        <span className="font-mono text-muted-foreground">
                          {fact.period}
                        </span>
                      </>
                    )}
                  </div>

                  <Badge
                    variant="outline"
                    className={`text-[11px] font-mono ${
                      fact.confidence >= 0.8
                        ? "border-emerald-500/30 text-emerald-400 bg-emerald-500/10"
                        : fact.confidence >= 0.5
                        ? "border-amber-500/30 text-amber-400 bg-amber-500/10"
                        : "border-rose-500/30 text-rose-400 bg-rose-500/10"
                    }`}
                  >
                    {Math.round(fact.confidence * 100)}% confidence
                  </Badge>
                </div>

                <div className="flex items-baseline gap-2">
                  <span className="font-mono text-xl font-bold tracking-tight text-foreground">
                    {fact.raw_value}
                  </span>
                  {fact.currency && (
                    <span className="font-mono text-xs text-muted-foreground">
                      ({fact.currency})
                    </span>
                  )}
                  {fact.norm_value !== null &&
                    fact.norm_value !== undefined &&
                    String(fact.norm_value) !== fact.raw_value && (
                      <span className="font-mono text-xs text-muted-foreground">
                        [norm: {fact.norm_value}{" "}
                        {fact.norm_unit || ""}]
                      </span>
                    )}
                </div>

                {/* Model / Prompt version monospace line */}
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] font-mono text-muted-foreground border-t border-border/50 pt-2 mt-1">
                  <span>
                    model: <span className="text-foreground/80">{fact.model}</span>
                  </span>
                  <span>·</span>
                  <span>
                    prompt: <span className="text-foreground/80">{fact.prompt_ver}</span>
                  </span>
                  {fact.scope && (
                    <>
                      <span>·</span>
                      <span>
                        scope: <span className="text-foreground/80">{fact.scope}</span>
                      </span>
                    </>
                  )}
                </div>
              </div>

              {/* Verbatim quote Alert */}
              <Alert className="border-border/80 bg-zinc-900/60 py-3">
                <Quote className="size-4 text-emerald-400" />
                <AlertTitle className="text-xs font-medium text-foreground mb-1">
                  Verbatim Source Quote
                </AlertTitle>
                <AlertDescription className="font-mono text-xs leading-relaxed text-zinc-200">
                  "{fact.quote}"
                </AlertDescription>
              </Alert>

              {/* Page Viewer with bounding box */}
              <div className="space-y-1.5">
                <div className="flex items-center justify-between text-xs font-semibold text-foreground">
                  <span className="flex items-center gap-1.5">
                    <Sparkles className="size-3.5 text-emerald-400" />
                    Spatial Page Evidence
                  </span>
                  {fact.bbox && (
                    <span className="font-mono text-[10px] text-muted-foreground">
                      bbox: [{fact.bbox.join(", ")}]
                    </span>
                  )}
                </div>

                <BBoxPageViewer
                  documentId={fact.document_id}
                  page={fact.page || 1}
                  bbox={fact.bbox}
                  filename={fact.document_filename}
                  quote={fact.quote}
                />
              </div>

              <Separator className="bg-border/60" />

              {/* Accordions: Cross-document relations & Lineage */}
              <Accordion
                className="w-full space-y-2"
              >
                {/* Cross-document relations Accordion */}
                <AccordionItem
                  value="relations"
                  className="rounded-lg border border-border/70 bg-card/40 px-3.5"
                >
                  <AccordionTrigger className="hover:no-underline py-3">
                    <div className="flex items-center gap-2 text-xs font-semibold">
                      <Layers className="size-4 text-emerald-400" />
                      <span>Cross-Document Relations</span>
                      <Badge
                        variant="secondary"
                        className="size-5 rounded-full p-0 flex items-center justify-center text-[10px]"
                      >
                        {fact.relations?.length || 0}
                      </Badge>
                    </div>
                  </AccordionTrigger>
                  <AccordionContent className="pt-1 pb-3 text-xs space-y-3">
                    {fact.relations && fact.relations.length > 0 ? (
                      fact.relations.map((rel, idx) => (
                        <div
                          key={rel.relation_id || idx}
                          className="rounded-md border border-border/70 bg-background/80 p-3 space-y-2"
                        >
                          <div className="flex items-center justify-between gap-2">
                            <RelationBadge relation={rel.relation} size="sm" />
                            {rel.counterpart_id && onSelectCounterpart && (
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() =>
                                  onSelectCounterpart(rel.counterpart_id)
                                }
                                className="h-6 px-2 text-[11px] text-muted-foreground hover:text-foreground"
                              >
                                View Counterpart
                                <ExternalLink className="size-3 ml-1" />
                              </Button>
                            )}
                          </div>

                          <p className="text-xs text-foreground/90 leading-relaxed">
                            {rel.explanation}
                          </p>

                          {rel.rules_applied && rel.rules_applied.length > 0 && (
                            <div className="flex flex-wrap items-center gap-1 pt-1">
                              <span className="text-[10px] text-muted-foreground font-mono">
                                Rules:
                              </span>
                              {rel.rules_applied.map((rule) => (
                                <Badge
                                  key={rule}
                                  variant="outline"
                                  className="font-mono text-[10px] px-1.5 py-0 bg-muted/40"
                                >
                                  {rule}
                                </Badge>
                              ))}
                            </div>
                          )}

                          {rel.quote && (
                            <div className="mt-1 rounded bg-muted/30 p-2 text-[11px] font-mono text-muted-foreground border-l-2 border-border">
                              <span className="text-foreground/70 font-sans font-semibold">
                                Counterpart quote:{" "}
                              </span>
                              "{rel.quote}"
                              {rel.document_filename && (
                                <span className="block mt-0.5 text-[10px] text-muted-foreground font-sans">
                                  Source: {rel.document_filename} (p. {rel.page || 1})
                                </span>
                              )}
                            </div>
                          )}
                        </div>
                      ))
                    ) : (
                      <p className="text-xs text-muted-foreground italic py-1">
                        No cross-document conflicts or corroborations detected for this fact.
                      </p>
                    )}
                  </AccordionContent>
                </AccordionItem>

                {/* Lineage Accordion */}
                <AccordionItem
                  value="lineage"
                  className="rounded-lg border border-border/70 bg-card/40 px-3.5"
                >
                  <AccordionTrigger className="hover:no-underline py-3">
                    <div className="flex items-center gap-2 text-xs font-semibold">
                      <History className="size-4 text-emerald-400" />
                      <span>Audit Trail & Provenance</span>
                      <Badge
                        variant="secondary"
                        className="size-5 rounded-full p-0 flex items-center justify-center text-[10px]"
                      >
                        {auditRows.length}
                      </Badge>
                    </div>
                  </AccordionTrigger>
                  <AccordionContent className="pt-1 pb-3 text-xs space-y-2">
                    {auditRows.length > 0 ? (
                      <div className="space-y-2 font-mono text-[11px]">
                        {auditRows.map((row) => (
                          <div
                            key={row.id}
                            className="rounded border border-border/50 bg-background/50 p-2 space-y-1"
                          >
                            <div className="flex items-center justify-between text-[10px] text-muted-foreground">
                              <span className="font-semibold text-emerald-400">
                                {row.action}
                              </span>
                              <span>{new Date(row.at).toLocaleTimeString()}</span>
                            </div>
                            {row.meta && (
                              <pre className="text-[10px] text-muted-foreground overflow-x-auto p-1 bg-muted/20 rounded">
                                {JSON.stringify(row.meta, null, 2)}
                              </pre>
                            )}
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="space-y-1 text-[11px] text-muted-foreground">
                        <p>OCR Provider: PyMuPDF Native / Groq Vision</p>
                        <p>Extraction Model: {fact.model}</p>
                        <p>Prompt Version: {fact.prompt_ver}</p>
                      </div>
                    )}
                  </AccordionContent>
                </AccordionItem>
              </Accordion>
            </div>
          ) : null}
        </ScrollArea>
      </SheetContent>
    </Sheet>
  );
}
