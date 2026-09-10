"use client";

import React from "react";
import { TimelineBlock } from "@/lib/research-protocol";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Clock, ExternalLink } from "lucide-react";
import { cn } from "@/lib/utils";

interface DynamicTimelineProps {
  block: TimelineBlock;
  onOpenEvidence?: (factId: string) => void;
  className?: string;
}

export function DynamicTimeline({
  block,
  onOpenEvidence,
  className,
}: DynamicTimelineProps) {
  const { title, events } = block;

  return (
    <div
      id={block.id}
      className={cn(
        "rounded-xl border border-border/80 bg-card/60 p-4 transition-all hover:border-border shadow-xs space-y-4",
        className
      )}
    >
      <div className="flex items-center gap-2">
        <Clock className="size-4 text-emerald-400" />
        <h4 className="text-sm font-semibold tracking-tight text-foreground">
          {title}
        </h4>
      </div>

      <div className="relative pl-6 space-y-6 before:absolute before:left-2.5 before:top-2 before:bottom-2 before:w-[1.5px] before:bg-border/60">
        {events.map((evt, idx) => (
          <div key={idx} className="relative space-y-1 group">
            {/* Timeline node dot */}
            <div className="absolute -left-6 top-1.5 size-3 rounded-full border-2 border-background bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.6)]" />

            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="font-mono text-xs font-semibold text-foreground">
                {evt.title}
              </span>
              <div className="flex items-center gap-2">
                {evt.tag && (
                  <Badge variant="outline" className="text-[9px] font-mono px-1.5 py-0">
                    {evt.tag}
                  </Badge>
                )}
                <span className="font-mono text-[11px] text-emerald-400">
                  {evt.date}
                </span>
              </div>
            </div>

            <p className="text-xs text-muted-foreground leading-relaxed">
              {evt.description}
            </p>

            {evt.factId && onOpenEvidence && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => onOpenEvidence(evt.factId!)}
                className="h-5 px-1.5 text-[10px] font-mono text-emerald-400 hover:text-emerald-300 -ml-1.5"
              >
                <span>[F:{evt.factId.slice(0, 6)}] View filing source</span>
                <ExternalLink className="size-2.5 ml-1" />
              </Button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
