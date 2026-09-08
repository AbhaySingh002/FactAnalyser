"use client";

import React, { useState, useEffect, useMemo } from "react";
import {
  Network,
  RotateCcw,
  ZoomIn,
  ZoomOut,
  Info,
  AlertTriangle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { Fact, RelationRow, RelationType } from "@/lib/types";
import { EvidenceSheet } from "@/components/EvidenceSheet";
import { cn } from "@/lib/utils";

interface GraphNode {
  id: string;
  label: string;
  sublabel: string;
  entity: string;
  attribute: string;
  value: string;
  x: number;
  y: number;
  vx: number;
  vy: number;
}

interface GraphEdge {
  id: string;
  source: string;
  target: string;
  relation: RelationType;
  explanation: string;
}

export default function GraphPage() {
  const [facts, setFacts] = useState<Fact[]>([]);
  const [relations, setRelations] = useState<RelationRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Evidence Sheet
  const [selectedFactId, setSelectedFactId] = useState<string | null>(null);
  const [sheetOpen, setSheetOpen] = useState(false);

  // Graph interaction
  const [zoom, setZoom] = useState(1.0);
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null);
  const [filterRelation, setFilterRelation] = useState<string>("all");

  const loadGraphData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [factsData, relsData] = await Promise.all([
        api.getFacts({ limit: 60 }),
        api.getRelations(),
      ]);
      setFacts(factsData);
      setRelations(relsData);
    } catch (err: any) {
      setError(err?.message || "Failed to load graph data");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadGraphData();
  }, []);

  // Compute node positions with a clean circular/cluster layout
  const { nodes, edges, nodeMap } = useMemo(() => {
    if (facts.length === 0) {
      return { nodes: [], edges: [], nodeMap: new Map<string, GraphNode>() };
    }

    const width = 850;
    const height = 550;
    const cx = width / 2;
    const cy = height / 2;

    // Group facts by entity
    const entityGroups: Record<string, Fact[]> = {};
    for (const f of facts) {
      const ent = f.entity_canon || f.entity || "Unknown";
      if (!entityGroups[ent]) entityGroups[ent] = [];
      entityGroups[ent].push(f);
    }

    const entities = Object.keys(entityGroups);
    const nEntities = entities.length || 1;
    const nodeList: GraphNode[] = [];
    const nMap = new Map<string, GraphNode>();

    entities.forEach((ent, eIdx) => {
      const groupFacts = entityGroups[ent];
      const entityAngle = (2 * Math.PI * eIdx) / nEntities;
      // Cluster center
      const clusterRadius = nEntities > 1 ? Math.min(width, height) * 0.28 : 0;
      const clusterX = cx + clusterRadius * Math.cos(entityAngle);
      const clusterY = cy + clusterRadius * Math.sin(entityAngle);

      groupFacts.forEach((f, fIdx) => {
        const localRadius = 50 + (fIdx % 3) * 35;
        const localAngle = (2 * Math.PI * fIdx) / groupFacts.length;
        const x = clusterX + (groupFacts.length > 1 ? localRadius * Math.cos(localAngle) : 0);
        const y = clusterY + (groupFacts.length > 1 ? localRadius * Math.sin(localAngle) : 0);

        const node: GraphNode = {
          id: f.id,
          label: f.attribute_canon || f.attribute,
          sublabel: f.raw_value,
          entity: ent,
          attribute: f.attribute_canon || f.attribute,
          value: f.raw_value,
          x: Math.max(40, Math.min(width - 40, x)),
          y: Math.max(40, Math.min(height - 40, y)),
          vx: 0,
          vy: 0,
        };
        nodeList.push(node);
        nMap.set(f.id, node);
      });
    });

    // Build edges from relations
    const edgeList: GraphEdge[] = [];
    for (const r of relations) {
      if (nMap.has(r.a_id) && nMap.has(r.b_id)) {
        edgeList.push({
          id: r.id,
          source: r.a_id,
          target: r.b_id,
          relation: r.relation,
          explanation: r.explanation,
        });
      }
    }

    return { nodes: nodeList, edges: edgeList, nodeMap: nMap };
  }, [facts, relations]);

  const filteredEdges = useMemo(() => {
    if (filterRelation === "all") return edges;
    return edges.filter((e) => e.relation === filterRelation);
  }, [edges, filterRelation]);

  const handleNodeClick = (nodeId: string) => {
    setSelectedFactId(nodeId);
    setSheetOpen(true);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-border/60 pb-5">
        <div>
          <div className="flex items-center gap-2">
            <Network className="size-5 text-emerald-400" />
            <h1 className="text-2xl font-bold tracking-tight text-foreground">
              Knowledge Graph Visualization
            </h1>
          </div>
          <p className="text-xs sm:text-sm text-muted-foreground mt-0.5">
            Topological map of extracted claims connected by corroborating and conflicting edges.
          </p>
        </div>

        <div className="flex items-center gap-2">
          {/* Zoom controls */}
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setZoom((z) => Math.max(0.6, +(z - 0.2).toFixed(1)))}
            disabled={zoom <= 0.6}
            className="size-8 p-0 text-muted-foreground hover:text-foreground"
          >
            <ZoomOut className="size-4" />
          </Button>
          <span className="min-w-[2.5rem] text-center font-mono text-xs text-muted-foreground">
            {Math.round(zoom * 100)}%
          </span>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setZoom((z) => Math.min(2.0, +(z + 0.2).toFixed(1)))}
            disabled={zoom >= 2.0}
            className="size-8 p-0 text-muted-foreground hover:text-foreground"
          >
            <ZoomIn className="size-4" />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setZoom(1.0)}
            className="size-8 p-0 text-muted-foreground hover:text-foreground"
          >
            <RotateCcw className="size-3.5" />
          </Button>
        </div>
      </div>

      {/* Filter Tabs */}
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-xs font-mono text-muted-foreground">Relation Filter:</span>
        {["all", "corroborates", "contradicts", "contextual_variance"].map((key) => (
          <Button
            key={key}
            variant="ghost"
            size="sm"
            onClick={() => setFilterRelation(key)}
            className={cn(
              "h-7 px-2.5 text-xs font-mono rounded-full border transition-all",
              filterRelation === key
                ? "bg-accent text-foreground border-border font-semibold shadow-xs"
                : "text-muted-foreground border-transparent hover:border-border/60 hover:text-foreground"
            )}
          >
            {key === "all"
              ? "All Edges"
              : key === "corroborates"
              ? "Corroborates"
              : key === "contradicts"
              ? "Contradicts"
              : "Variance"}
          </Button>
        ))}
      </div>

      {/* Main SVG Graph Container */}
      <Card className="border-border/80 bg-zinc-950/80 overflow-hidden shadow-sm relative">
        <CardContent className="p-0">
          {loading ? (
            <div className="h-[550px] flex items-center justify-center">
              <Skeleton className="h-[500px] w-[800px] rounded-lg" />
            </div>
          ) : error ? (
            <div className="h-[400px] flex flex-col items-center justify-center text-center p-6 space-y-2">
              <AlertTriangle className="size-7 text-rose-400" />
              <p className="text-sm font-medium">{error}</p>
              <Button size="sm" variant="outline" onClick={loadGraphData}>
                Retry
              </Button>
            </div>
          ) : nodes.length === 0 ? (
            <div className="h-[400px] flex flex-col items-center justify-center text-center p-6 space-y-2">
              <Network className="size-8 text-muted-foreground" />
              <p className="text-sm font-medium">No facts available for graph visualization</p>
              <p className="text-xs text-muted-foreground">
                Upload filings from the Dashboard to extract nodes and build relations.
              </p>
            </div>
          ) : (
            <div className="w-full overflow-auto flex justify-center p-4">
              <svg
                width={850 * zoom}
                height={550 * zoom}
                viewBox="0 0 850 550"
                className="select-none transition-transform"
              >
                <defs>
                  {/* Subtle radial background glow */}
                  <radialGradient id="graphGlow" cx="50%" cy="50%" r="50%">
                    <stop offset="0%" stopColor="#34d399" stopOpacity="0.05" />
                    <stop offset="100%" stopColor="#000000" stopOpacity="0" />
                  </radialGradient>
                </defs>

                <rect width="850" height="550" fill="url(#graphGlow)" />

                {/* Edges */}
                <g className="edges">
                  {filteredEdges.map((edge) => {
                    const sourceNode = nodeMap.get(edge.source);
                    const targetNode = nodeMap.get(edge.target);
                    if (!sourceNode || !targetNode) return null;

                    const color =
                      edge.relation === "contradicts"
                        ? "#f43f5e" // rose
                        : edge.relation === "corroborates"
                        ? "#34d399" // emerald
                        : edge.relation === "contextual_variance"
                        ? "#fbbf24" // amber
                        : "#a1a1aa"; // zinc

                    const isDashed = edge.relation === "contextual_variance";

                    return (
                      <g key={edge.id} className="group">
                        <line
                          x1={sourceNode.x}
                          y1={sourceNode.y}
                          x2={targetNode.x}
                          y2={targetNode.y}
                          stroke={color}
                          strokeWidth="2"
                          strokeOpacity="0.6"
                          strokeDasharray={isDashed ? "4 4" : undefined}
                          className="transition-all hover:stroke-width-3 hover:stroke-opacity-100 cursor-pointer"
                        />
                      </g>
                    );
                  })}
                </g>

                {/* Nodes */}
                <g className="nodes">
                  {nodes.map((node) => {
                    const isHovered = hoveredNodeId === node.id;

                    return (
                      <g
                        key={node.id}
                        transform={`translate(${node.x}, ${node.y})`}
                        onClick={() => handleNodeClick(node.id)}
                        onMouseEnter={() => setHoveredNodeId(node.id)}
                        onMouseLeave={() => setHoveredNodeId(null)}
                        className="cursor-pointer group"
                      >
                        {/* Glow halo on hover */}
                        <circle
                          r={isHovered ? 26 : 18}
                          fill="#34d399"
                          fillOpacity={isHovered ? 0.2 : 0.08}
                          className="transition-all duration-150"
                        />

                        {/* Node circle */}
                        <circle
                          r="14"
                          fill="#18181b"
                          stroke={isHovered ? "#34d399" : "#3f3f46"}
                          strokeWidth={isHovered ? "2.5" : "1.5"}
                          className="transition-all"
                        />

                        {/* Node center dot */}
                        <circle
                          r="4"
                          fill={isHovered ? "#34d399" : "#a1a1aa"}
                          className="transition-colors"
                        />

                        {/* Node text label */}
                        <text
                          y="26"
                          textAnchor="middle"
                          fill="#fafafa"
                          fontSize="10"
                          fontFamily="monospace"
                          fontWeight="600"
                          className="pointer-events-none drop-shadow-md"
                        >
                          {node.label}
                        </text>

                        {/* Value sublabel */}
                        <text
                          y="37"
                          textAnchor="middle"
                          fill="#34d399"
                          fontSize="9"
                          fontFamily="monospace"
                          className="pointer-events-none drop-shadow-md"
                        >
                          {node.value}
                        </text>
                      </g>
                    );
                  })}
                </g>
              </svg>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Legend & Instructions Card */}
      <div className="flex flex-wrap items-center justify-between gap-4 rounded-lg border border-border/70 bg-card/40 px-4 py-3 text-xs">
        <div className="flex flex-wrap items-center gap-4 text-muted-foreground">
          <span className="font-mono text-foreground font-semibold flex items-center gap-1.5">
            <Info className="size-3.5 text-emerald-400" />
            Graph Legend:
          </span>
          <div className="flex items-center gap-1.5">
            <span className="size-2 rounded-full bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.7)]" />
            <span>Corroborates (Solid Emerald)</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="size-2 rounded-full bg-rose-400 shadow-[0_0_6px_rgba(244,63,94,0.7)]" />
            <span>Contradicts (Solid Rose)</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="size-2 rounded-full bg-amber-400 shadow-[0_0_6px_rgba(251,191,36,0.7)]" />
            <span>Contextual Variance (Dashed Amber)</span>
          </div>
        </div>

        <span className="text-[11px] font-mono text-emerald-400">
          Click any node to view bounding-box evidence →
        </span>
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
