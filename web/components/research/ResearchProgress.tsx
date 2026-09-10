"use client";

import React, { useState } from "react";
import { ResearchStep } from "@/lib/research-protocol";
import {
  Sparkles,
  ChevronDown,
  ChevronRight,
  CheckCircle2,
  Loader2,
  Search,
  FileCheck,
} from "lucide-react";
import { cn } from "@/lib/utils";

interface ResearchProgressProps {
  steps: ResearchStep[];
  isSearching?: boolean;
  className?: string;
}

export function ResearchProgress({
  steps,
  isSearching = false,
  className,
}: ResearchProgressProps) {
  const [expanded, setExpanded] = useState(false);

  if (!steps || steps.length === 0) return null;

  const completedCount = steps.filter((s) => s.status === "completed").length;
  const currentStep = steps.find((s) => s.status === "running") || steps[steps.length - 1];
  const allCompleted = completedCount === steps.length && !isSearching;

  return (
    <div
      className={cn(
        "rounded-lg border border-border/60 bg-muted/20 text-xs transition-all overflow-hidden",
        className
      )}
    >
      {/* Subtle Accordion Header / Pill */}
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-3 py-2 text-left hover:bg-muted/40 transition-colors select-none"
      >
        <div className="flex items-center gap-2 min-w-0">
          {allCompleted ? (
            <div className="size-4 rounded-full bg-emerald-500/10 text-emerald-400 flex items-center justify-center shrink-0">
              <CheckCircle2 className="size-3" />
            </div>
          ) : (
            <div className="size-4 rounded-full bg-emerald-500/10 text-emerald-400 flex items-center justify-center shrink-0">
              <Sparkles className="size-2.5 animate-pulse" />
            </div>
          )}

          <div className="flex items-center gap-2 truncate">
            <span className="font-mono text-[11px] font-semibold text-foreground">
              {allCompleted
                ? `Research completed (${completedCount} operations)`
                : `Researching...`}
            </span>
            <span className="text-muted-foreground text-[11px] truncate hidden sm:inline">
              • {currentStep?.title}
            </span>
          </div>
        </div>

        <div className="flex items-center gap-1.5 text-muted-foreground text-[11px] shrink-0 ml-2">
          <span className="font-mono">{completedCount}/{steps.length}</span>
          {expanded ? (
            <ChevronDown className="size-3.5" />
          ) : (
            <ChevronRight className="size-3.5" />
          )}
        </div>
      </button>

      {/* Expanded Step Details */}
      {expanded && (
        <div className="px-3 pb-3 pt-1 border-t border-border/40 space-y-2">
          {steps.map((step, idx) => {
            const isDone = step.status === "completed";
            const isRun = step.status === "running";

            return (
              <div
                key={step.id || idx}
                className="flex items-start gap-2 text-[11px] font-mono leading-tight"
              >
                <div className="mt-0.5 shrink-0">
                  {isDone ? (
                    <CheckCircle2 className="size-3 text-emerald-400" />
                  ) : isRun ? (
                    <Loader2 className="size-3 text-emerald-400 animate-spin" />
                  ) : (
                    <div className="size-2 rounded-full bg-muted-foreground/30 ml-0.5" />
                  )}
                </div>

                <div className="flex-1 space-y-0.5">
                  <div className="flex items-center justify-between gap-2">
                    <span
                      className={cn(
                        isDone
                          ? "text-foreground/90 font-medium"
                          : isRun
                          ? "text-emerald-400 font-semibold"
                          : "text-muted-foreground/60"
                      )}
                    >
                      {step.title}
                    </span>
                    {step.sourcesCount && (
                      <span className="text-[10px] text-muted-foreground">
                        {step.sourcesCount} sources
                      </span>
                    )}
                  </div>

                  {step.query && (
                    <div className="flex items-center gap-1 text-[10px] text-muted-foreground bg-muted/40 rounded px-1.5 py-0.5 w-fit">
                      <Search className="size-2.5 text-emerald-400" />
                      <span>{step.query}</span>
                    </div>
                  )}

                  {step.detail && (
                    <p className="text-[10px] text-muted-foreground">
                      {step.detail}
                    </p>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
