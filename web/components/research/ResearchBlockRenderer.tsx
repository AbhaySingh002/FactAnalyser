"use client";

import React from "react";
import { ResearchBlock } from "@/lib/research-protocol";
import { DynamicChart } from "./DynamicChart";
import { DynamicTable } from "./DynamicTable";
import { DynamicFindings } from "./DynamicFindings";
import { DynamicMetrics } from "./DynamicMetrics";
import { DynamicTimeline } from "./DynamicTimeline";
import { FileText, ExternalLink } from "lucide-react";
import { Button } from "@/components/ui/button";

interface ResearchBlockRendererProps {
  block: ResearchBlock;
  onOpenEvidence?: (factId: string) => void;
  className?: string;
}

export function ResearchBlockRenderer({
  block,
  onOpenEvidence,
  className,
}: ResearchBlockRendererProps) {
  switch (block.type) {
    case "chart":
      return (
        <DynamicChart
          block={block}
          onOpenEvidence={onOpenEvidence}
          className={className}
        />
      );

    case "table":
      return (
        <DynamicTable
          block={block}
          onOpenEvidence={onOpenEvidence}
          className={className}
        />
      );

    case "finding":
      return (
        <DynamicFindings
          block={block}
          onOpenEvidence={onOpenEvidence}
          className={className}
        />
      );

    case "metrics":
      return <DynamicMetrics block={block} className={className} />;

    case "timeline":
      return (
        <DynamicTimeline
          block={block}
          onOpenEvidence={onOpenEvidence}
          className={className}
        />
      );

    case "sources":
      return (
        <div
          id={block.id}
          className="rounded-xl border border-border/80 bg-card/60 p-4 space-y-2.5 shadow-xs"
        >
          <div className="flex items-center gap-2 text-xs font-semibold tracking-tight text-foreground">
            <FileText className="size-3.5 text-emerald-400" />
            <span>{block.title || "Referenced Due-Diligence Sources"}</span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {block.sources.map((src, idx) => (
              <div
                key={idx}
                onClick={() => onOpenEvidence && onOpenEvidence(src.fact_id)}
                className="flex items-center justify-between gap-2 p-2.5 rounded-lg border border-border/60 bg-muted/30 hover:bg-muted/70 hover:border-border cursor-pointer transition-colors group"
              >
                <div className="min-w-0 space-y-0.5">
                  <div className="flex items-center gap-1.5 font-mono text-[11px] font-semibold text-emerald-400">
                    <span>[F:{src.fact_id.slice(0, 6)}]</span>
                    {src.page && (
                      <span className="text-muted-foreground text-[10px]">
                        p.{src.page}
                      </span>
                    )}
                  </div>
                  {src.filename && (
                    <p className="text-xs text-foreground/90 truncate">
                      {src.filename}
                    </p>
                  )}
                  {src.quote && (
                    <p className="text-[10px] text-muted-foreground italic truncate">
                      &ldquo;{src.quote}&rdquo;
                    </p>
                  )}
                </div>

                <ExternalLink className="size-3 text-muted-foreground group-hover:text-emerald-400 shrink-0 transition-colors" />
              </div>
            ))}
          </div>
        </div>
      );

    default:
      return null;
  }
}
