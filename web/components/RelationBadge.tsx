import React from "react";
import { Badge } from "@/components/ui/badge";
import { RelationType } from "@/lib/types";
import { cn } from "@/lib/utils";

interface RelationBadgeProps {
  relation: RelationType | string | null | undefined;
  showDot?: boolean;
  className?: string;
  size?: "sm" | "default";
}

export const RELATION_CONFIG: Record<
  RelationType,
  { label: string; bg: string; text: string; border: string; dot: string }
> = {
  corroborates: {
    label: "Corroborates",
    bg: "bg-emerald-500/10",
    text: "text-emerald-400",
    border: "border-emerald-500/30",
    dot: "bg-emerald-400",
  },
  contradicts: {
    label: "Contradicts",
    bg: "bg-rose-500/10",
    text: "text-rose-400",
    border: "border-rose-500/30",
    dot: "bg-rose-400",
  },
  contextual_variance: {
    label: "Contextual Variance",
    bg: "bg-amber-500/10",
    text: "text-amber-400",
    border: "border-amber-500/30",
    dot: "bg-amber-400",
  },
  needs_review: {
    label: "Needs Review",
    bg: "bg-zinc-500/15",
    text: "text-zinc-400",
    border: "border-zinc-500/30",
    dot: "bg-zinc-400",
  },
};

export function RelationBadge({
  relation,
  showDot = true,
  className,
  size = "default",
}: RelationBadgeProps) {
  if (!relation || !(relation in RELATION_CONFIG)) {
    return (
      <Badge
        variant="outline"
        className={cn(
          "font-mono font-normal text-muted-foreground border-border/60 bg-muted/20",
          size === "sm" ? "px-1.5 py-0 text-[10px]" : "text-xs",
          className
        )}
      >
        Single Source
      </Badge>
    );
  }

  const config = RELATION_CONFIG[relation as RelationType];

  return (
    <Badge
      variant="outline"
      className={cn(
        "font-medium border inline-flex items-center gap-1.5 transition-colors",
        config.bg,
        config.text,
        config.border,
        size === "sm" ? "px-1.5 py-0 text-[10px]" : "px-2 py-0.5 text-xs",
        className
      )}
    >
      {showDot && (
        <span
          className={cn(
            "rounded-full shrink-0",
            config.dot,
            size === "sm" ? "size-1.5" : "size-2"
          )}
        />
      )}
      <span>{config.label}</span>
    </Badge>
  );
}
