/**
 * Research Protocol & Structured Block Protocol
 * Defines the contract for structured AI analysis responses, research states, and dynamic visual artifacts.
 */

import { Citation } from "./types";

export type ChartType = "line" | "bar" | "donut" | "area";

export interface ChartSeriesConfig {
  dataKey: string;
  label: string;
  color?: string;
}

export interface ChartBlock {
  id: string;
  type: "chart";
  chartType: ChartType;
  title: string;
  description?: string;
  data: Array<Record<string, string | number>>;
  config: {
    xAxisKey?: string;
    series: ChartSeriesConfig[];
  };
  source?: string;
}

export interface TableColumn {
  key: string;
  label: string;
  align?: "left" | "right" | "center";
}

export interface TableBlock {
  id: string;
  type: "table";
  title: string;
  description?: string;
  columns: TableColumn[];
  rows: Array<Record<string, any>>;
  source?: string;
}

export interface FindingBlock {
  id: string;
  type: "finding";
  title: string;
  category: "contradiction" | "corroboration" | "variance" | "insight";
  content: string;
  evidence?: string;
  factId?: string;
  confidence?: number;
}

export interface MetricItem {
  label: string;
  value: string;
  change?: string;
  period?: string;
  badge?: string;
  trend?: "up" | "down" | "neutral";
}

export interface MetricBlock {
  id: string;
  type: "metrics";
  title?: string;
  items: MetricItem[];
}

export interface TimelineEvent {
  date: string;
  title: string;
  description: string;
  tag?: string;
  factId?: string;
}

export interface TimelineBlock {
  id: string;
  type: "timeline";
  title: string;
  events: TimelineEvent[];
}

export interface SourcesBlock {
  id: string;
  type: "sources";
  title?: string;
  sources: Citation[];
}

export type ResearchBlock =
  | ChartBlock
  | TableBlock
  | FindingBlock
  | MetricBlock
  | TimelineBlock
  | SourcesBlock;

export interface ResearchStep {
  id: string;
  title: string;
  status: "pending" | "running" | "completed" | "failed";
  query?: string;
  sourcesCount?: number;
  detail?: string;
}

export interface ResearchArtifact {
  id: string;
  type: "chart" | "table" | "metrics" | "finding";
  title: string;
  blockId: string;
  summary: string;
}


