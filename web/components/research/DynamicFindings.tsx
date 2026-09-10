"use client";

import React from "react";
import { FindingBlock } from "@/lib/research-protocol";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  Sparkles,
  Quote,
  ExternalLink,
} from "lucide-react";
import { cn } from "@/lib/utils";

interface DynamicFindingsProps {
  block: FindingBlock;
  onOpenEvidence?: (factId: string) => void;
  className?: string;
}

export function DynamicFindings({
  block,
  onOpenEvidence,
  className,
}: DynamicFindingsProps) {
  const { title, category, content, evidence, factId, confidence } = block;

  const config = {
    contradiction: {
      icon: AlertTriangle,
      badgeText: "Contradiction",
      borderClass: "border-rose-500/30",
      bgClass: "bg-rose-500/5",
      badgeClass: "border-rose-500/40 bg-rose-500/10 text-rose-400",
      iconClass: "text-rose-400",
    },
    corroboration: {
      icon: CheckCircle2,
      badgeText: "Corroborated",
      borderClass: "border-emerald-500/30",
      bgClass: "bg-emerald-500/5",
      badgeClass: "border-emerald-500/40 bg-emerald-500/10 text-emerald-400",
      iconClass: "text-emerald-400",
    },
    variance: {
      icon: Clock,
      badgeText: "Contextual Variance",
      borderClass: "border-amber-500/30",
      bgClass: "bg-amber-500/5",
      badgeClass: "border-amber-500/40 bg-amber-500/10 text-amber-400",
      iconClass: "text-amber-400",
    },
    insight: {
      icon: Sparkles,
      badgeText: "Key Finding",
      borderClass: "border-sky-500/30",
      bgClass: "bg-sky-500/5",
      badgeClass: "border-sky-500/40 bg-sky-500/10 text-sky-400",
      iconClass: "text-sky-400",
    },
  }[category] || {
    icon: Sparkles,
    badgeText: "Analysis Note",
    borderClass: "border-border/80",
    bgClass: "bg-card/60",
    badgeClass: "border-border text-foreground",
    iconClass: "text-emerald-400",
  };

  const IconComponent = config.icon;

  return (
    <div
      id={block.id}
      className={cn(
        "rounded-xl border p-4 transition-all shadow-xs space-y-2.5",
        config.borderClass,
        config.bgClass,
        className
      )}
    >
      {/* Header */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 min-w-0">
          <IconComponent className={cn("size-4 shrink-0", config.iconClass)} />
          <h4 className="text-sm font-semibold tracking-tight text-foreground truncate">
            {title}
          </h4>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          {confidence !== undefined && (
            <span className="text-[10px] font-mono text-muted-foreground">
              Conf: {Math.round(confidence * 100)}%
            </span>
          )}
          <Badge variant="outline" className={cn("text-[10px] font-mono", config.badgeClass)}>
            {config.badgeText}
          </Badge>
        </div>
      </div>

      {/* Narrative content */}
      <p className="text-xs text-foreground/90 leading-relaxed pl-6">
        {content}
      </p>

      {/* Supporting quote & coordinate trigger */}
      {evidence && (
        <div className="ml-6 mt-2 rounded-lg border border-border/60 bg-muted/40 p-2.5 space-y-1.5">
          <div className="flex items-center justify-between gap-2">
            <span className="text-[10px] font-mono text-muted-foreground uppercase flex items-center gap-1">
              <Quote className="size-3 text-emerald-400" />
              Source Evidence Quote:
            </span>
            {factId && onOpenEvidence && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => onOpenEvidence(factId)}
                className="h-6 px-2 text-[10px] font-mono text-emerald-400 hover:text-emerald-300 hover:bg-emerald-500/10"
              >
                <span>[F:{factId.slice(0, 6)}] Inspect coordinates</span>
                <ExternalLink className="size-2.5 ml-1" />
              </Button>
            )}
          </div>
          <p className="text-[11px] text-muted-foreground italic leading-relaxed">
            &ldquo;{evidence}&rdquo;
          </p>
        </div>
      )}
    </div>
  );
}
