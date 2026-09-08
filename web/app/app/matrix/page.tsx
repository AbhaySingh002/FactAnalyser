"use client";

import React, { useState, useEffect, useMemo } from "react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Search,
  RotateCcw,
  AlertTriangle,
  FileSpreadsheet,
  Info,
} from "lucide-react";
import { api } from "@/lib/api";
import { MatrixData, Fact } from "@/lib/types";
import { RelationBadge } from "@/components/RelationBadge";
import { EvidenceSheet } from "@/components/EvidenceSheet";
import { cn } from "@/lib/utils";

export default function MatrixPage() {
  const [matrixData, setMatrixData] = useState<MatrixData | null>(null);
  const [factsMap, setFactsMap] = useState<Record<string, Fact>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [searchQuery, setSearchQuery] = useState("");
  const [filterRelation, setFilterRelation] = useState<string>("all");

  // Evidence Sheet State
  const [selectedFactId, setSelectedFactId] = useState<string | null>(null);
  const [sheetOpen, setSheetOpen] = useState(false);

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [matrix, factsList] = await Promise.all([
        api.getMatrix(),
        api.getFacts({ limit: 100 }),
      ]);
      setMatrixData(matrix);

      const fMap: Record<string, Fact> = {};
      for (const f of factsList) {
        fMap[f.id] = f;
      }
      setFactsMap(fMap);
    } catch (err: any) {
      setError(err?.message || "Failed to load matrix data");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleCellClick = (factId: string) => {
    setSelectedFactId(factId);
    setSheetOpen(true);
  };

  // Filter entities and attributes based on user search
  const filteredEntities = useMemo(() => {
    if (!matrixData) return [];
    if (!searchQuery.trim()) return matrixData.entities;
    const q = searchQuery.toLowerCase();
    return matrixData.entities.filter((e) => e.toLowerCase().includes(q));
  }, [matrixData, searchQuery]);

  const filteredAttributes = useMemo(() => {
    if (!matrixData) return [];
    if (!searchQuery.trim()) return matrixData.attributes;
    const q = searchQuery.toLowerCase();
    const hasMatchingEntity = matrixData.entities.some((e) => e.toLowerCase().includes(q));
    if (hasMatchingEntity) return matrixData.attributes;
    return matrixData.attributes.filter((attr) => attr.toLowerCase().includes(q));
  }, [matrixData, searchQuery]);

  // Count relations for stats bar
  const stats = useMemo(() => {
    if (!matrixData) return { totalCells: 0, contradicts: 0, corroborates: 0, variance: 0 };
    let contradicts = 0;
    let corroborates = 0;
    let variance = 0;
    let totalCells = 0;

    for (const cell of Object.values(matrixData.cells)) {
      if (cell.fact_ids && cell.fact_ids.length > 0) {
        totalCells++;
        if (cell.badge === "contradicts") contradicts++;
        else if (cell.badge === "corroborates") corroborates++;
        else if (cell.badge === "contextual_variance") variance++;
      }
    }

    return { totalCells, contradicts, corroborates, variance };
  }, [matrixData]);

  return (
    <div className="space-y-6">
      {/* Header and KPI cards */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-border/60 pb-5">
        <div>
          <div className="flex items-center gap-2">
            <FileSpreadsheet className="size-5 text-emerald-400" />
            <h1 className="text-2xl font-bold tracking-tight text-foreground">
              Fact Knowledge Matrix
            </h1>
          </div>
          <p className="text-xs sm:text-sm text-muted-foreground mt-0.5">
            Cross-document reconciliation matrix. Every cell is linked to cryptographic source evidence.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={loadData}
            disabled={loading}
            className="h-8 px-2.5 text-xs text-muted-foreground hover:text-foreground border-border/80"
          >
            <RotateCcw className={`size-3.5 mr-1.5 ${loading ? "animate-spin" : ""}`} />
            Refresh Matrix
          </Button>
        </div>
      </div>

      {/* KPI Stats Bar */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="rounded-lg border border-border/70 bg-card/60 p-3">
          <div className="text-[11px] font-mono text-muted-foreground">RECONCILED FACTS</div>
          <div className="text-xl font-bold text-foreground font-mono mt-0.5">
            {stats.totalCells}
          </div>
        </div>

        <div className="rounded-lg border border-rose-500/20 bg-rose-500/5 p-3">
          <div className="text-[11px] font-mono text-rose-400">CONTRADICTIONS</div>
          <div className="text-xl font-bold text-rose-400 font-mono mt-0.5">
            {stats.contradicts}
          </div>
        </div>

        <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-3">
          <div className="text-[11px] font-mono text-emerald-400">CORROBORATIONS</div>
          <div className="text-xl font-bold text-emerald-400 font-mono mt-0.5">
            {stats.corroborates}
          </div>
        </div>

        <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-3">
          <div className="text-[11px] font-mono text-amber-400">CONTEXTUAL VARIANCES</div>
          <div className="text-xl font-bold text-amber-400 font-mono mt-0.5">
            {stats.variance}
          </div>
        </div>
      </div>

      {/* Search and Filters */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2 flex-1 max-w-sm">
          <div className="relative w-full">
            <Search className="absolute left-2.5 top-2.5 size-3.5 text-muted-foreground" />
            <Input
              placeholder="Filter entities or attributes..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="h-8 pl-8 text-xs bg-muted/30 border-border/80"
            />
          </div>
        </div>

        {/* Status filter buttons */}
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className="text-[11px] text-muted-foreground font-mono mr-1">Filter:</span>
          {["all", "contradicts", "corroborates", "contextual_variance"].map((filterKey) => (
            <Button
              key={filterKey}
              variant="ghost"
              size="sm"
              onClick={() => setFilterRelation(filterKey)}
              className={cn(
                "h-7 px-2.5 text-[11px] font-mono rounded-full border transition-all",
                filterRelation === filterKey
                  ? "bg-accent text-foreground border-border font-semibold shadow-xs"
                  : "text-muted-foreground border-transparent hover:border-border/60 hover:text-foreground"
              )}
            >
              {filterKey === "all"
                ? "All Cells"
                : filterKey === "contradicts"
                ? "Contradictions"
                : filterKey === "corroborates"
                ? "Corroborations"
                : "Variance"}
            </Button>
          ))}
        </div>
      </div>

      {/* Main Fact Matrix Table */}
      <div className="rounded-lg border border-border/80 bg-card/60 shadow-sm overflow-hidden">
        {loading ? (
          <div className="p-8 space-y-4">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-14 w-full" />
            <Skeleton className="h-14 w-full" />
            <Skeleton className="h-14 w-full" />
          </div>
        ) : error ? (
          <div className="p-12 text-center space-y-3">
            <AlertTriangle className="size-7 text-rose-400 mx-auto" />
            <p className="text-sm font-medium">{error}</p>
            <Button size="sm" variant="outline" onClick={loadData}>
              Retry
            </Button>
          </div>
        ) : !matrixData || matrixData.entities.length === 0 ? (
          <div className="p-16 text-center space-y-3">
            <FileSpreadsheet className="size-10 text-muted-foreground/60 mx-auto" />
            <p className="text-sm font-semibold text-foreground">Fact Matrix is Empty</p>
            <p className="text-xs text-muted-foreground max-w-sm mx-auto">
              Upload documents from the Dashboard to extract facts and build the cross-reconciliation matrix.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto max-h-[600px] relative">
            <Table className="border-collapse text-xs">
              <TableHeader className="sticky top-0 z-20 bg-zinc-950/95 backdrop-blur shadow-xs">
                <TableRow className="border-b border-border/80">
                  {/* Sticky Entity Column Header */}
                  <TableHead className="sticky left-0 z-30 bg-zinc-950/95 w-[200px] min-w-[180px] font-mono text-xs font-semibold text-foreground border-r border-border/80">
                    Entity / Company
                  </TableHead>

                  {/* Attribute Headers */}
                  {filteredAttributes.map((attr) => (
                    <TableHead
                      key={attr}
                      className="min-w-[170px] px-3 font-mono text-xs font-semibold text-foreground border-r border-border/40"
                    >
                      <div className="flex flex-col">
                        <span className="truncate" title={attr}>
                          {attr}
                        </span>
                      </div>
                    </TableHead>
                  ))}
                </TableRow>
              </TableHeader>

              <TableBody>
                {filteredEntities.map((entity) => (
                  <TableRow
                    key={entity}
                    className="border-b border-border/60 hover:bg-muted/30 transition-colors"
                  >
                    {/* Sticky Entity Column */}
                    <TableCell className="sticky left-0 z-10 bg-background/95 backdrop-blur font-semibold text-foreground border-r border-border/80 text-xs py-3">
                      <span className="font-mono text-xs truncate block" title={entity}>
                        {entity}
                      </span>
                    </TableCell>

                    {/* Attribute Cells */}
                    {filteredAttributes.map((attr) => {
                      const cellKey = `${entity}|${attr}`;
                      const cell = matrixData.cells[cellKey];
                      const factIds = cell?.fact_ids || [];
                      const badge = cell?.badge;

                      // Filter logic by relation type
                      if (
                        filterRelation !== "all" &&
                        badge !== filterRelation
                      ) {
                        return (
                          <TableCell
                            key={cellKey}
                            className="p-2 border-r border-border/40 opacity-30"
                          >
                            <span className="text-muted-foreground/30 font-mono text-[11px]">—</span>
                          </TableCell>
                        );
                      }

                      if (factIds.length === 0) {
                        return (
                          <TableCell
                            key={cellKey}
                            className="p-2 text-center text-muted-foreground/40 font-mono text-xs border-r border-border/40"
                          >
                            —
                          </TableCell>
                        );
                      }

                      const primaryFactId = factIds[0];
                      const factObj = factsMap[primaryFactId];
                      const displayValue = factObj?.raw_value || "View Fact";
                      const period = factObj?.period;

                      // Tooltip explanation text
                      const tooltipText =
                        badge === "contradicts"
                          ? "Direct numerical conflict detected across multiple documents."
                          : badge === "corroborates"
                          ? "Fact corroborated across independent source documents."
                          : badge === "contextual_variance"
                          ? "Variations in period, accounting scope, or reporting entities."
                          : "Single source observation extracted from document.";

                      return (
                        <TableCell
                          key={cellKey}
                          className="p-2 border-r border-border/40"
                        >
                          <Tooltip>
                            <TooltipTrigger
                              onClick={() => handleCellClick(primaryFactId)}
                              className="w-full text-left"
                            >
                              <div className="flex flex-col gap-1 rounded-md p-1.5 transition-all hover:bg-muted/60 cursor-pointer border border-transparent hover:border-border/70 group">
                                <div className="flex items-center justify-between gap-1">
                                  <span className="font-mono font-bold text-foreground text-xs truncate group-hover:text-emerald-400 transition-colors">
                                    {displayValue}
                                  </span>
                                  {badge && (
                                    <span
                                      className={cn(
                                        "size-2 rounded-full shrink-0",
                                        badge === "contradicts"
                                          ? "bg-rose-400 shadow-[0_0_6px_rgba(244,63,94,0.7)]"
                                          : badge === "corroborates"
                                          ? "bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.7)]"
                                          : badge === "contextual_variance"
                                          ? "bg-amber-400 shadow-[0_0_6px_rgba(251,191,36,0.7)]"
                                          : "bg-zinc-400"
                                      )}
                                    />
                                  )}
                                </div>

                                <div className="flex items-center justify-between text-[10px] font-mono text-muted-foreground">
                                  {period ? (
                                    <span className="truncate">{period}</span>
                                  ) : (
                                    <span className="italic opacity-60">unspecified</span>
                                  )}
                                  {factIds.length > 1 && (
                                    <Badge
                                      variant="secondary"
                                      className="px-1 py-0 text-[9px] font-mono h-3.5"
                                    >
                                      +{factIds.length - 1} docs
                                    </Badge>
                                  )}
                                </div>
                              </div>
                            </TooltipTrigger>
                            <TooltipContent side="top" className="max-w-xs text-xs p-2">
                              <p className="font-semibold mb-0.5 flex items-center gap-1.5">
                                {badge ? (
                                  <RelationBadge relation={badge} size="sm" />
                                ) : (
                                  "Single Fact"
                                )}
                              </p>
                              <p className="text-[11px] text-muted-foreground leading-normal">
                                {tooltipText}
                              </p>
                              <p className="text-[10px] text-emerald-400 font-mono mt-1">
                                Click cell to inspect bounding-box evidence →
                              </p>
                            </TooltipContent>
                          </Tooltip>
                        </TableCell>
                      );
                    })}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </div>

      {/* Legend Card */}
      <div className="flex flex-wrap items-center gap-4 rounded-lg border border-border/70 bg-card/40 px-4 py-2.5 text-xs text-muted-foreground">
        <span className="font-mono text-foreground font-semibold flex items-center gap-1.5">
          <Info className="size-3.5 text-emerald-400" />
          Matrix Legend:
        </span>
        <div className="flex items-center gap-1.5">
          <span className="size-2 rounded-full bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.7)]" />
          <span>Corroborates (Identical claims across independent filings)</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="size-2 rounded-full bg-rose-400 shadow-[0_0_6px_rgba(244,63,94,0.7)]" />
          <span>Contradicts (Direct numerical discrepancies)</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="size-2 rounded-full bg-amber-400 shadow-[0_0_6px_rgba(251,191,36,0.7)]" />
          <span>Contextual Variance (Period or scope divergence)</span>
        </div>
      </div>

      {/* Reusable Evidence Sheet */}
      <EvidenceSheet
        factId={selectedFactId}
        open={sheetOpen}
        onOpenChange={setSheetOpen}
        onSelectCounterpart={(counterpartId) => setSelectedFactId(counterpartId)}
      />
    </div>
  );
}
