"use client";

import React, { useMemo } from "react";
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  AreaChart,
  Area,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
} from "recharts";
import { ChartBlock } from "@/lib/research-protocol";
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  ChartConfig,
} from "@/components/ui/chart";
import { FileText, TrendingUp } from "lucide-react";
import { cn } from "@/lib/utils";

const DEFAULT_COLORS = [
  "#34d399", // emerald
  "#38bdf8", // sky
  "#f43f5e", // rose
  "#fbbf24", // amber
  "#a78bfa", // violet
  "#fb923c", // orange
];

interface DynamicChartProps {
  block: ChartBlock;
  onOpenEvidence?: (factId: string) => void;
  className?: string;
}

export function DynamicChart({ block, className }: DynamicChartProps) {
  const { chartType, data, config, title, description, source } = block;

  const chartConfig = useMemo<ChartConfig>(() => {
    const cfg: ChartConfig = {};
    (config.series || []).forEach((s, idx) => {
      cfg[s.dataKey] = {
        label: s.label,
        color: s.color || DEFAULT_COLORS[idx % DEFAULT_COLORS.length],
      };
    });
    return cfg;
  }, [config.series]);

  const xAxisKey = config.xAxisKey || "period";

  return (
    <div
      id={block.id}
      className={cn(
        "rounded-xl border border-border/80 bg-card/60 p-4 transition-all hover:border-border shadow-xs space-y-3",
        className
      )}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-0.5">
          <h4 className="text-sm font-semibold tracking-tight text-foreground flex items-center gap-2">
            <TrendingUp className="size-4 text-emerald-400 shrink-0" />
            {title}
          </h4>
          {description && (
            <p className="text-xs text-muted-foreground">{description}</p>
          )}
        </div>
      </div>

      {/* Chart visualization */}
      <div className="w-full pt-1">
        {chartType === "line" && (
          <ChartContainer config={chartConfig} className="h-64 w-full">
            <LineChart
              data={data}
              margin={{ top: 12, right: 12, left: -16, bottom: 0 }}
            >
              <CartesianGrid vertical={false} strokeDasharray="3 3" />
              <XAxis
                dataKey={xAxisKey}
                tickLine={false}
                axisLine={false}
                tickMargin={8}
                fontSize={11}
              />
              <YAxis
                tickLine={false}
                axisLine={false}
                tickMargin={8}
                fontSize={11}
              />
              <ChartTooltip content={<ChartTooltipContent />} />
              {config.series.map((s, idx) => (
                <Line
                  key={s.dataKey}
                  type="monotone"
                  dataKey={s.dataKey}
                  name={s.label}
                  stroke={s.color || DEFAULT_COLORS[idx % DEFAULT_COLORS.length]}
                  strokeWidth={2.5}
                  dot={{ r: 3, fill: s.color || DEFAULT_COLORS[idx % DEFAULT_COLORS.length] }}
                  activeDot={{ r: 5 }}
                />
              ))}
            </LineChart>
          </ChartContainer>
        )}

        {chartType === "bar" && (
          <ChartContainer config={chartConfig} className="h-64 w-full">
            <BarChart
              data={data}
              margin={{ top: 12, right: 12, left: -16, bottom: 0 }}
            >
              <CartesianGrid vertical={false} strokeDasharray="3 3" />
              <XAxis
                dataKey={xAxisKey}
                tickLine={false}
                axisLine={false}
                tickMargin={8}
                fontSize={11}
              />
              <YAxis
                tickLine={false}
                axisLine={false}
                tickMargin={8}
                fontSize={11}
              />
              <ChartTooltip content={<ChartTooltipContent />} />
              {config.series.map((s, idx) => (
                <Bar
                  key={s.dataKey}
                  dataKey={s.dataKey}
                  name={s.label}
                  fill={s.color || DEFAULT_COLORS[idx % DEFAULT_COLORS.length]}
                  radius={[4, 4, 0, 0]}
                />
              ))}
            </BarChart>
          </ChartContainer>
        )}

        {chartType === "area" && (
          <ChartContainer config={chartConfig} className="h-64 w-full">
            <AreaChart
              data={data}
              margin={{ top: 12, right: 12, left: -16, bottom: 0 }}
            >
              <CartesianGrid vertical={false} strokeDasharray="3 3" />
              <XAxis
                dataKey={xAxisKey}
                tickLine={false}
                axisLine={false}
                tickMargin={8}
                fontSize={11}
              />
              <YAxis
                tickLine={false}
                axisLine={false}
                tickMargin={8}
                fontSize={11}
              />
              <ChartTooltip content={<ChartTooltipContent />} />
              {config.series.map((s, idx) => {
                const col = s.color || DEFAULT_COLORS[idx % DEFAULT_COLORS.length];
                return (
                  <Area
                    key={s.dataKey}
                    type="monotone"
                    dataKey={s.dataKey}
                    name={s.label}
                    stroke={col}
                    fill={col}
                    fillOpacity={0.2}
                    strokeWidth={2}
                  />
                );
              })}
            </AreaChart>
          </ChartContainer>
        )}

        {chartType === "donut" && (
          <ChartContainer config={chartConfig} className="h-64 w-full">
            <PieChart>
              <ChartTooltip content={<ChartTooltipContent />} />
              <Pie
                data={data}
                dataKey={config.series[0]?.dataKey || "value"}
                nameKey={xAxisKey}
                innerRadius={55}
                outerRadius={80}
                paddingAngle={4}
              >
                {data.map((_, index) => (
                  <Cell
                    key={`cell-${index}`}
                    fill={DEFAULT_COLORS[index % DEFAULT_COLORS.length]}
                  />
                ))}
              </Pie>
            </PieChart>
          </ChartContainer>
        )}
      </div>

      {/* Footer & Source Attribution */}
      {source && (
        <div className="pt-2 border-t border-border/50 flex items-center justify-between text-[10px] font-mono text-muted-foreground">
          <span className="flex items-center gap-1 truncate max-w-sm">
            <FileText className="size-3 text-emerald-400 shrink-0" />
            Source: {source}
          </span>
          <span className="text-emerald-400/90 font-medium">Reconciled series</span>
        </div>
      )}
    </div>
  );
}
