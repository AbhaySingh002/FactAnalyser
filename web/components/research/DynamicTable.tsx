"use client";

import React, { useState, useMemo } from "react";
import { TableBlock } from "@/lib/research-protocol";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Table as TableIcon,
  Search,
  ArrowUpDown,
  Download,
  Copy,
  Check,
  FileText,
} from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

interface DynamicTableProps {
  block: TableBlock;
  onOpenEvidence?: (factId: string) => void;
  className?: string;
}

export function DynamicTable({ block, onOpenEvidence, className }: DynamicTableProps) {
  const { title, description, columns, rows, source } = block;

  const [search, setSearch] = useState("");
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("asc");
  const [copied, setCopied] = useState(false);

  // Sorting handler
  const handleSort = (key: string) => {
    if (sortKey === key) {
      setSortOrder((prev) => (prev === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortOrder("asc");
    }
  };

  // Filter and sort rows
  const processedRows = useMemo(() => {
    let result = [...rows];

    if (search.trim()) {
      const q = search.toLowerCase();
      result = result.filter((row) =>
        Object.values(row).some((val) =>
          String(val ?? "")
            .toLowerCase()
            .includes(q)
        )
      );
    }

    if (sortKey) {
      result.sort((a, b) => {
        const valA = a[sortKey];
        const valB = b[sortKey];
        if (typeof valA === "number" && typeof valB === "number") {
          return sortOrder === "asc" ? valA - valB : valB - valA;
        }
        return sortOrder === "asc"
          ? String(valA ?? "").localeCompare(String(valB ?? ""))
          : String(valB ?? "").localeCompare(String(valA ?? ""));
      });
    }

    return result;
  }, [rows, search, sortKey, sortOrder]);

  // Export as CSV
  const handleCopyCsv = () => {
    if (!columns.length || !rows.length) return;
    const headerLine = columns.map((c) => `"${c.label}"`).join(",");
    const rowLines = processedRows.map((r) =>
      columns.map((c) => `"${String(r[c.key] ?? "").replace(/"/g, '""')}"`).join(",")
    );
    const csvContent = [headerLine, ...rowLines].join("\n");

    navigator.clipboard.writeText(csvContent);
    setCopied(true);
    toast.success("Table copied to clipboard as CSV");
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div
      id={block.id}
      className={cn(
        "rounded-xl border border-border/80 bg-card/60 p-4 transition-all hover:border-border shadow-xs space-y-3",
        className
      )}
    >
      {/* Header & Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="space-y-0.5">
          <h4 className="text-sm font-semibold tracking-tight text-foreground flex items-center gap-2">
            <TableIcon className="size-4 text-emerald-400 shrink-0" />
            {title}
          </h4>
          {description && (
            <p className="text-xs text-muted-foreground">{description}</p>
          )}
        </div>

        <div className="flex items-center gap-2">
          <div className="relative">
            <Search className="absolute left-2.5 top-2.5 size-3.5 text-muted-foreground" />
            <Input
              placeholder="Filter rows..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="h-8 pl-8 text-xs w-36 sm:w-44 bg-muted/30 border-border/70"
            />
          </div>

          <Button
            variant="outline"
            size="sm"
            onClick={handleCopyCsv}
            className="h-8 px-2.5 text-xs text-muted-foreground hover:text-foreground border-border/80 shrink-0"
            title="Copy as CSV"
          >
            {copied ? (
              <Check className="size-3.5 text-emerald-400 mr-1" />
            ) : (
              <Copy className="size-3.5 mr-1" />
            )}
            CSV
          </Button>
        </div>
      </div>

      {/* Table Content */}
      <div className="rounded-lg border border-border/70 overflow-hidden bg-background/50">
        <div className="overflow-x-auto max-h-[360px]">
          <Table className="text-xs">
            <TableHeader className="sticky top-0 z-10 bg-muted/50 backdrop-blur-md">
              <TableRow className="border-b border-border/70 hover:bg-transparent">
                {columns.map((col) => (
                  <TableHead
                    key={col.key}
                    onClick={() => handleSort(col.key)}
                    className="cursor-pointer select-none font-mono text-[11px] font-semibold text-foreground hover:text-emerald-400 transition-colors py-2.5 px-3"
                  >
                    <div
                      className={cn(
                        "flex items-center gap-1.5",
                        col.align === "right" ? "justify-end" : ""
                      )}
                    >
                      <span>{col.label}</span>
                      <ArrowUpDown className="size-3 opacity-40 hover:opacity-100" />
                    </div>
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {processedRows.length === 0 ? (
                <TableRow>
                  <TableCell
                    colSpan={columns.length}
                    className="text-center py-6 text-xs text-muted-foreground"
                  >
                    No matching records found.
                  </TableCell>
                </TableRow>
              ) : (
                processedRows.map((row, rIdx) => (
                  <TableRow
                    key={rIdx}
                    className="border-b border-border/40 hover:bg-muted/30 transition-colors"
                  >
                    {columns.map((col) => {
                      const val = row[col.key];
                      const isStatus =
                        col.key.toLowerCase().includes("status") ||
                        col.key.toLowerCase().includes("relation");

                      return (
                        <TableCell
                          key={col.key}
                          className={cn(
                            "py-2.5 px-3 font-mono text-xs",
                            col.align === "right" ? "text-right" : "text-left"
                          )}
                        >
                          {isStatus && typeof val === "string" ? (
                            <Badge
                              variant="outline"
                              className={cn(
                                "text-[10px] font-mono px-1.5 py-0",
                                val.toLowerCase().includes("contradict")
                                  ? "border-rose-500/40 bg-rose-500/10 text-rose-400"
                                  : val.toLowerCase().includes("corroborat")
                                  ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-400"
                                  : val.toLowerCase().includes("var")
                                  ? "border-amber-500/40 bg-amber-500/10 text-amber-400"
                                  : "border-border text-muted-foreground"
                              )}
                            >
                              {val}
                            </Badge>
                          ) : (
                            <span className="text-foreground/90">{val ?? "—"}</span>
                          )}
                        </TableCell>
                      );
                    })}
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </div>
      </div>

      {/* Footer & Source */}
      {source && (
        <div className="pt-1.5 border-t border-border/50 flex items-center justify-between text-[10px] font-mono text-muted-foreground">
          <span className="flex items-center gap-1 truncate max-w-sm">
            <FileText className="size-3 text-emerald-400 shrink-0" />
            Source: {source}
          </span>
          <span>{processedRows.length} rows reconciled</span>
        </div>
      )}
    </div>
  );
}
