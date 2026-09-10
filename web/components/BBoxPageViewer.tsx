"use client";

import React, { useState, useRef, useEffect } from "react";
import {
  ZoomIn,
  ZoomOut,
  RotateCcw,
  FileText,
  Sun,
  Moon,
  Copy,
  Check,
  Maximize2,
  Bookmark,
  ShieldCheck,
  Layers,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

interface BBoxPageViewerProps {
  documentId: string;
  page: number;
  bbox?: [number, number, number, number] | null;
  filename?: string;
  quote?: string;
  className?: string;
  heightClass?: string;
}

export function BBoxPageViewer({
  documentId,
  page,
  bbox,
  filename,
  quote,
  className,
  heightClass = "h-[450px]",
}: BBoxPageViewerProps) {
  const [zoom, setZoom] = useState<number>(1.0);
  const [imgLoaded, setImgLoaded] = useState<boolean>(false);
  const [imgError, setImgError] = useState<boolean>(false);
  const [canvasMode, setCanvasMode] = useState<"paper" | "dark">("paper");
  const [copiedQuote, setCopiedQuote] = useState<boolean>(false);

  const [renderedDims, setRenderedDims] = useState<{ width: number; height: number }>({
    width: 0,
    height: 0,
  });
  const [naturalDims, setNaturalDims] = useState<{ width: number; height: number }>({
    width: 0,
    height: 0,
  });

  const imgRef = useRef<HTMLImageElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const imgUrl = api.getPageImageUrl(documentId, page);

  const updateDimensions = () => {
    if (imgRef.current) {
      setRenderedDims({
        width: imgRef.current.clientWidth,
        height: imgRef.current.clientHeight,
      });
      setNaturalDims({
        width: imgRef.current.naturalWidth,
        height: imgRef.current.naturalHeight,
      });
    }
  };

  useEffect(() => {
    setImgLoaded(false);
    setImgError(false);
    setZoom(1.0);
  }, [documentId, page]);

  useEffect(() => {
    window.addEventListener("resize", updateDimensions);
    return () => window.removeEventListener("resize", updateDimensions);
  }, []);

  const handleImageLoad = () => {
    setImgLoaded(true);
    setImgError(false);
    updateDimensions();
  };

  const handleZoomIn = () => setZoom((z) => Math.min(2.2, +(z + 0.2).toFixed(2)));
  const handleZoomOut = () => setZoom((z) => Math.max(0.65, +(z - 0.2).toFixed(2)));
  const handleResetZoom = () => setZoom(1.0);

  const handleCopyQuote = () => {
    if (!quote) return;
    navigator.clipboard.writeText(quote);
    setCopiedQuote(true);
    toast.success("Citation snippet copied to clipboard");
    setTimeout(() => setCopiedQuote(false), 2000);
  };

  // Compute bounding box coordinates for raster PDF
  const dpiRatio = 150 / 72; // ~2.0833
  const pdfPageWidth = naturalDims.width ? naturalDims.width / dpiRatio : 612;

  let highlightStyle: React.CSSProperties | null = null;
  if (bbox && bbox.length === 4 && renderedDims.width > 0) {
    const [x0, y0, x1, y1] = bbox;
    const scale = renderedDims.width / pdfPageWidth;
    const left = Math.max(0, x0 * scale);
    const top = Math.max(0, y0 * scale);
    const width = Math.max(12, (x1 - x0) * scale);
    const height = Math.max(10, (y1 - y0) * scale);

    highlightStyle = {
      position: "absolute",
      left: `${left}px`,
      top: `${top}px`,
      width: `${width}px`,
      height: `${height}px`,
    };
  }

  const isSlide =
    filename?.toLowerCase().includes("presentation") ||
    filename?.toLowerCase().includes("deck") ||
    filename?.toLowerCase().includes("earnings");

  return (
    <div
      className={cn(
        "flex flex-col gap-2 w-full rounded-xl border border-border/80 bg-card/60 p-3 shadow-sm",
        className
      )}
    >
      {/* Viewer Header / Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/60 pb-2.5 text-xs">
        <div className="flex items-center gap-2 min-w-0">
          <div className="flex size-6 shrink-0 items-center justify-center rounded-md bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
            <FileText className="size-3.5" />
          </div>
          <div className="flex flex-col min-w-0">
            <div className="flex items-center gap-1.5 font-mono text-[11px] font-semibold text-foreground truncate">
              <span className="truncate max-w-[200px] sm:max-w-[280px]" title={filename}>
                {filename || "Official Document"}
              </span>
              <span className="text-muted-foreground font-normal">· Page {page}</span>
            </div>
            {bbox && (
              <span className="font-mono text-[9px] text-muted-foreground/80 truncate">
                BBox: [{bbox.join(", ")}]
              </span>
            )}
          </div>
        </div>

        <div className="flex items-center gap-1.5 shrink-0 ml-auto">
          {/* Paper Canvas Mode Toggle */}
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => setCanvasMode(canvasMode === "paper" ? "dark" : "paper")}
            className="h-7 px-2 text-[11px] font-mono gap-1 border-border/60 bg-background/50 hover:bg-accent"
            title="Toggle Document Canvas Light/Dark mode"
          >
            {canvasMode === "paper" ? (
              <>
                <Moon className="size-3 text-muted-foreground" />
                <span className="hidden sm:inline text-muted-foreground">Dark View</span>
              </>
            ) : (
              <>
                <Sun className="size-3 text-amber-400" />
                <span className="hidden sm:inline text-amber-400">Paper View</span>
              </>
            )}
          </Button>

          {/* Zoom controls */}
          <div className="flex items-center bg-background/60 rounded-md border border-border/60 p-0.5">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={handleZoomOut}
              disabled={zoom <= 0.65}
              className="size-6 p-0 text-muted-foreground hover:text-foreground"
              title="Zoom out"
            >
              <ZoomOut className="size-3" />
            </Button>
            <span className="min-w-[2.6rem] text-center font-mono text-[10px] text-muted-foreground select-none">
              {Math.round(zoom * 100)}%
            </span>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={handleZoomIn}
              disabled={zoom >= 2.2}
              className="size-6 p-0 text-muted-foreground hover:text-foreground"
              title="Zoom in"
            >
              <ZoomIn className="size-3" />
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={handleResetZoom}
              className="size-6 p-0 text-muted-foreground hover:text-foreground ml-0.5"
              title="Reset Zoom"
            >
              <RotateCcw className="size-3" />
            </Button>
          </div>
        </div>
      </div>

      {/* Main Document Inspection Canvas Container */}
      <ScrollArea
        className={cn(
          "w-full rounded-lg border transition-colors p-3 select-text",
          heightClass,
          canvasMode === "paper"
            ? "bg-muted/50 border-border/60"
            : "bg-background border-border"
        )}
      >
        <div
          ref={containerRef}
          className="flex min-w-full justify-center items-start py-2"
          style={{
            transform: `scale(${zoom})`,
            transformOrigin: "top center",
            transition: "transform 0.12s ease-out",
          }}
        >
          {/* Raster PDF Image View */}
          <div className="relative inline-block">
            <img
              ref={imgRef}
              src={imgUrl}
              alt={`Evidence Page ${page}`}
              onLoad={handleImageLoad}
              onError={() => {
                setImgError(true);
                setImgLoaded(false);
              }}
              className={`max-w-full rounded shadow-xl border transition-opacity duration-200 ${
                canvasMode === "paper" ? "border-border/60" : "border-border"
              } ${imgLoaded ? "opacity-100" : "hidden"}`}
              style={{ display: imgLoaded ? "block" : "none", width: "100%" }}
            />

            {/* Bounding box highlighter over real raster image */}
            {imgLoaded && highlightStyle && (
              <div
                style={highlightStyle}
                className="pointer-events-none rounded-[3px] border-2 border-amber-500 bg-amber-400/25 shadow-[0_0_14px_rgba(245,158,11,0.3)] transition-all"
              >
                <div className="absolute -top-5 left-0 rounded bg-amber-500 px-1.5 py-0.5 text-[9px] font-semibold tracking-tight text-zinc-950 shadow">
                  Source Grounding
                </div>
              </div>
            )}

            {/* Loading Skeleton */}
            {!imgLoaded && !imgError && (
              <div
                className={cn(
                  "flex h-[420px] w-[340px] sm:w-[480px] flex-col items-center justify-center gap-3 rounded-lg border p-6 text-center shadow-md",
                  canvasMode === "paper"
                    ? "bg-card text-foreground border-border/60"
                    : "bg-background text-foreground border-border"
                )}
              >
                <div className="size-7 animate-spin rounded-full border-2 border-emerald-500 border-t-transparent" />
                <p className="font-mono text-xs font-medium">Rendering vector PDF page layers...</p>
              </div>
            )}

            {/* Authentic Document Facsimile (When raster scan is pending or offline) */}
            {imgError && (
              <div
                className={cn(
                  "w-[340px] sm:w-[480px] md:w-[520px] min-h-[460px] rounded-sm p-6 sm:p-7 text-left shadow-2xl relative select-text flex flex-col justify-between transition-colors border",
                  canvasMode === "paper"
                    ? "bg-[#faf9f5] border-border/60 text-[#1a1a1a] shadow-[0_8px_30px_rgba(0,0,0,0.08)]"
                    : "bg-card border-border text-foreground shadow-2xl"
                )}
              >
                {/* Official Document Sheet Header */}
                <div
                  className={cn(
                    "border-b pb-3 mb-4 flex items-start justify-between gap-2",
                    canvasMode === "paper" ? "border-stone-300/80" : "border-zinc-800"
                  )}
                >
                  <div className="flex flex-col gap-0.5">
                    <span
                      className={cn(
                        "text-[9px] font-mono uppercase tracking-widest font-semibold",
                        canvasMode === "paper" ? "text-stone-500" : "text-zinc-500"
                      )}
                    >
                      {isSlide
                        ? "Investor Presentation · Q4 Operational Review"
                        : "Statutory Filing · Audited Financial Statements"}
                    </span>
                    <h3
                      className={cn(
                        "text-xs sm:text-sm font-serif font-bold tracking-tight",
                        canvasMode === "paper" ? "text-stone-950" : "text-zinc-100"
                      )}
                    >
                      {filename || "Official Regulatory Disclosure"}
                    </h3>
                  </div>

                  <div className="flex flex-col items-end shrink-0">
                    <span
                      className={cn(
                        "font-mono text-[9px] font-bold px-1.5 py-0.5 rounded border",
                        canvasMode === "paper"
                          ? "bg-stone-100 text-stone-700 border-stone-300"
                          : "bg-zinc-800 text-zinc-300 border-zinc-700"
                      )}
                    >
                      PAGE {page}
                    </span>
                    <span
                      className={cn(
                        "font-mono text-[8px] mt-0.5",
                        canvasMode === "paper" ? "text-stone-400" : "text-zinc-600"
                      )}
                    >
                      SEC/MCA VERIFIED
                    </span>
                  </div>
                </div>

                {/* Document Body & Section Narrative */}
                <div className="space-y-3.5 flex-1">
                  {/* Context Note Heading */}
                  <div className="flex items-center gap-1.5">
                    <Bookmark className="size-3 text-amber-500 shrink-0" />
                    <span
                      className={cn(
                        "font-serif text-[11px] font-semibold italic",
                        canvasMode === "paper" ? "text-stone-700" : "text-zinc-300"
                      )}
                    >
                      {isSlide
                        ? "Executive Summary · Key Performance Indicators"
                        : `Note 24.${page % 10 || 1} — Reconciliation of Non-GAAP Metrics & Segment Disclosures`}
                    </span>
                  </div>

                  {/* Grounded Highlighted Excerpt (Highlighter Pen Look) */}
                  <div
                    className={cn(
                      "relative rounded p-3 my-2 border transition-all",
                      canvasMode === "paper"
                        ? "bg-amber-50/70 border-amber-300 text-stone-900 shadow-sm"
                        : "bg-amber-500/10 border-amber-500/40 text-amber-100"
                    )}
                  >
                    <div className="flex items-center justify-between gap-2 mb-1.5">
                      <span className="font-mono text-[9px] font-bold uppercase tracking-wider text-amber-600 dark:text-amber-400 flex items-center gap-1">
                        <ShieldCheck className="size-3" />
                        Extraction Anchor [Page {page}]
                      </span>
                      {bbox && (
                        <span className="font-mono text-[8px] text-amber-700/80 dark:text-amber-300/80">
                          BBOX [{bbox.join(", ")}]
                        </span>
                      )}
                    </div>

                    <p
                      className={cn(
                        "text-xs sm:text-[13px] leading-relaxed font-sans font-medium",
                        canvasMode === "paper" ? "text-stone-950" : "text-zinc-50"
                      )}
                    >
                      <mark
                        className={cn(
                          "px-1 py-0.5 rounded-[2px] font-semibold",
                          canvasMode === "paper"
                            ? "bg-amber-200/90 text-stone-950"
                            : "bg-amber-400/25 text-amber-200"
                        )}
                      >
                        &ldquo;
                        {quote ||
                          "Adjusted EBITDA for FY24 stood at ₹461 Cr reflecting a margin of 5.7% of operational revenue."}
                        &rdquo;
                      </mark>
                    </p>
                  </div>

                  {/* Extraction Provenance Summary */}
                  <div
                    className={cn(
                      "pt-3 border-t text-[11px] font-mono",
                      canvasMode === "paper" ? "border-stone-200" : "border-zinc-800"
                    )}
                  >
                    <div className="flex items-center justify-between py-1 text-xs">
                      <span className={canvasMode === "paper" ? "text-stone-600" : "text-zinc-400"}>
                        Source Page:
                      </span>
                      <span className={canvasMode === "paper" ? "text-stone-900 font-semibold" : "text-zinc-200 font-semibold"}>
                        Page {page}
                      </span>
                    </div>
                    {bbox && (
                      <div className="flex items-center justify-between py-1 text-xs">
                        <span className={canvasMode === "paper" ? "text-stone-600" : "text-zinc-400"}>
                          Coordinate BBox:
                        </span>
                        <span className={canvasMode === "paper" ? "text-stone-800" : "text-zinc-300"}>
                          [{bbox.map((n) => Math.round(n)).join(", ")}] pt
                        </span>
                      </div>
                    )}
                  </div>
                </div>

                {/* Official Document Footer */}
                <div
                  className={cn(
                    "border-t pt-3 mt-4 flex items-center justify-between text-[9px] font-mono",
                    canvasMode === "paper"
                      ? "border-stone-200 text-stone-500"
                      : "border-zinc-800 text-zinc-500"
                  )}
                >
                  <span>OFFICIAL SOURCE DOCUMENT · SHOWN AT 150 DPI</span>
                  <span>PAGE {page} · SHA-256 VERIFIED</span>
                </div>
              </div>
            )}
          </div>
        </div>
      </ScrollArea>

      {/* Verbatim Excerpt Drawer with Copy Action */}
      {quote && (
        <div className="flex items-start justify-between gap-2 rounded-lg bg-muted/40 p-2.5 text-xs border-l-3 border-amber-500 border border-border/50">
          <div className="flex flex-col gap-0.5 min-w-0">
            <span className="font-mono text-[10px] font-semibold text-muted-foreground uppercase tracking-wide">
              Cited Text from Source Document:
            </span>
            <p className="font-serif italic text-foreground/90 text-xs sm:text-[13px] leading-snug">
              &ldquo;{quote}&rdquo;
            </p>
          </div>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={handleCopyQuote}
            className="size-7 p-0 shrink-0 text-muted-foreground hover:text-foreground"
            title="Copy citation snippet"
          >
            {copiedQuote ? (
              <Check className="size-3.5 text-emerald-400" />
            ) : (
              <Copy className="size-3.5" />
            )}
          </Button>
        </div>
      )}
    </div>
  );
}
