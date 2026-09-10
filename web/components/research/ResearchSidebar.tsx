"use client";

import React from "react";
import {
  Compass,
  X,
  LineChart,
  Table,
  Layers,
  AlertTriangle,
  ChevronRight,
  Sparkles,
  FileCheck,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { ResearchArtifact, ResearchBlock } from "@/lib/research-protocol";
import { cn } from "@/lib/utils";

interface ResearchSidebarProps {
  artifacts: ResearchArtifact[];
  blocks: ResearchBlock[];
  onNavigateToBlock: (blockId: string) => void;
  open: boolean;
  onToggle: () => void;
}

export function ResearchSidebar({
  artifacts,
  blocks,
  onNavigateToBlock,
  open,
  onToggle,
}: ResearchSidebarProps) {
  const displayArtifacts = React.useMemo(() => {
    if (artifacts && artifacts.length > 0) return artifacts;
    return blocks.map((b) => ({
      id: `art-${b.id}`,
      blockId: b.id,
      title: "title" in b && b.title ? b.title : `${b.type.toUpperCase()} block`,
      summary:
        "description" in b && b.description
          ? b.description
          : "content" in b && b.content
          ? b.content
          : `Interactive financial ${b.type} extracted from analysis`,
      type: b.type as any,
    }));
  }, [artifacts, blocks]);

  if (!open) return null;

  const getArtifactIcon = (type: ResearchArtifact["type"]) => {
    switch (type) {
      case "chart":
        return <LineChart className="size-3.5 text-emerald-400" />;
      case "table":
        return <Table className="size-3.5 text-sky-400" />;
      case "finding":
        return <AlertTriangle className="size-3.5 text-amber-400" />;
      case "metrics":
        return <Layers className="size-3.5 text-indigo-400" />;
      default:
        return <FileCheck className="size-3.5 text-emerald-400" />;
    }
  };

  return (
    <aside className="absolute sm:relative right-0 top-0 bottom-0 w-full sm:w-80 border-l border-border/70 bg-background/95 sm:bg-card/40 backdrop-blur-md sm:backdrop-blur-none flex flex-col h-full shrink-0 z-30 transition-all duration-200 shadow-xl sm:shadow-none">
      {/* Header */}
      <div className="h-12 border-b border-border/70 px-4 flex items-center justify-between bg-background/50">
        <div className="flex items-center gap-2">
          <Compass className="size-4 text-emerald-400" />
          <span className="text-xs font-semibold text-foreground">Findings & Artifacts</span>
          {displayArtifacts.length > 0 && (
            <Badge variant="outline" className="text-[10px] font-mono px-1.5 py-0 h-4 border-emerald-500/30 text-emerald-400">
              {displayArtifacts.length}
            </Badge>
          )}
        </div>
        <Button
          variant="ghost"
          size="icon"
          onClick={onToggle}
          className="size-7 text-muted-foreground hover:text-foreground active:scale-95"
          title="Close findings sidebar"
        >
          <X className="size-3.5" />
        </Button>
      </div>

      {/* Content */}
      <ScrollArea className="flex-1 p-3">
        {displayArtifacts.length === 0 && blocks.length === 0 ? (
          <div className="p-6 text-center space-y-3 my-8">
            <div className="size-10 rounded-full bg-muted/40 border border-border flex items-center justify-center mx-auto text-muted-foreground">
              <Sparkles className="size-4 opacity-50" />
            </div>
            <div className="space-y-1">
              <p className="text-xs font-medium text-foreground">No findings generated yet</p>
              <p className="text-[11px] text-muted-foreground leading-relaxed">
                As research steps run, extracted charts, tables, and variance disclosures will appear here.
              </p>
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            {displayArtifacts.length > 0 && (
              <div className="space-y-2">
                <div className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground px-1">
                  Surfaced Artifacts ({displayArtifacts.length})
                </div>
                <div className="space-y-1.5">
                  {displayArtifacts.map((art) => (
                    <div
                      key={art.id}
                      onClick={() => onNavigateToBlock(art.blockId)}
                      className="group p-2.5 rounded-lg border border-border/60 bg-muted/20 hover:bg-muted/60 hover:border-border cursor-pointer transition-all active:scale-[0.98] space-y-1"
                    >
                      <div className="flex items-center justify-between gap-1.5">
                        <div className="flex items-center gap-1.5 min-w-0">
                          {getArtifactIcon(art.type)}
                          <span className="text-xs font-medium text-foreground truncate group-hover:text-emerald-400 transition-colors">
                            {art.title}
                          </span>
                        </div>
                        <ChevronRight className="size-3 text-muted-foreground group-hover:text-foreground group-hover:translate-x-0.5 transition-all shrink-0" />
                      </div>
                      <p className="text-[11px] text-muted-foreground line-clamp-2 pl-5">
                        {art.summary}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {blocks.length > 0 && (
              <div className="space-y-2 pt-2 border-t border-border/50">
                <div className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground px-1">
                  Document Blocks ({blocks.length})
                </div>
                <div className="space-y-1">
                  {blocks.map((block) => (
                    <button
                      key={block.id}
                      onClick={() => onNavigateToBlock(block.id)}
                      className="w-full text-left p-2 rounded-md hover:bg-muted/40 text-xs flex items-center justify-between text-muted-foreground hover:text-foreground transition-all active:scale-[0.98] cursor-pointer group"
                    >
                      <span className="truncate pr-2 font-mono text-[11px]">
                        {"title" in block && block.title ? block.title : block.type}
                      </span>
                      <Badge variant="outline" className="text-[9px] uppercase px-1 py-0 shrink-0 font-mono">
                        {block.type}
                      </Badge>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </ScrollArea>
    </aside>
  );
}
