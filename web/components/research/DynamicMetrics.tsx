"use client";

import React from "react";
import { MetricBlock } from "@/lib/research-protocol";
import { Badge } from "@/components/ui/badge";
import { TrendingUp, TrendingDown, Minus, Layers } from "lucide-react";
import { cn } from "@/lib/utils";

interface DynamicMetricsProps {
  block: MetricBlock;
  className?: string;
}

export function DynamicMetrics({ block, className }: DynamicMetricsProps) {
  const { title, items } = block;

  return (
    <div id={block.id} className={cn("space-y-2.5", className)}>
      {title && (
        <div className="flex items-center gap-2 text-xs font-semibold tracking-tight text-foreground">
          <Layers className="size-3.5 text-emerald-400" />
          <span>{title}</span>
        </div>
      )}

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
        {items.map((m, idx) => {
          const isUp = m.trend === "up";
          const isDown = m.trend === "down";

          return (
            <div
              key={idx}
              className="rounded-xl border border-border/80 bg-card/60 p-3 transition-all hover:border-border shadow-xs space-y-1"
            >
              <div className="flex items-center justify-between text-[11px] font-mono text-muted-foreground">
                <span className="truncate" title={m.label}>
                  {m.label}
                </span>
                {m.period && (
                  <span className="text-[10px] text-muted-foreground/80">
                    {m.period}
                  </span>
                )}
              </div>

              <div className="text-xl font-bold font-mono tracking-tight text-foreground">
                {m.value}
              </div>

              <div className="flex items-center justify-between gap-1.5 pt-0.5">
                {m.change && (
                  <div
                    className={cn(
                      "flex items-center gap-1 text-[10px] font-mono font-medium",
                      isUp
                        ? "text-emerald-400"
                        : isDown
                        ? "text-rose-400"
                        : "text-muted-foreground"
                    )}
                  >
                    {isUp ? (
                      <TrendingUp className="size-3" />
                    ) : isDown ? (
                      <TrendingDown className="size-3" />
                    ) : (
                      <Minus className="size-3" />
                    )}
                    <span>{m.change}</span>
                  </div>
                )}

                {m.badge && (
                  <Badge
                    variant="outline"
                    className="text-[9px] font-mono px-1 py-0 h-4 border-border/60 text-muted-foreground ml-auto"
                  >
                    {m.badge}
                  </Badge>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
