"use client";

import React, { useState, useRef, useEffect } from "react";
import { ZoomIn, ZoomOut, RotateCcw, FileText, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { api } from "@/lib/api";

interface BBoxPageViewerProps {
  documentId: string;
  page: number;
  bbox?: [number, number, number, number] | null;
  filename?: string;
  quote?: string;
}

export function BBoxPageViewer({
  documentId,
  page,
  bbox,
  filename,
  quote,
}: BBoxPageViewerProps) {
  const [zoom, setZoom] = useState<number>(1.0);
  const [imgLoaded, setImgLoaded] = useState<boolean>(false);
  const [imgError, setImgError] = useState<boolean>(false);
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

  const handleZoomIn = () => setZoom((z) => Math.min(2.5, +(z + 0.25).toFixed(2)));
  const handleZoomOut = () => setZoom((z) => Math.max(0.6, +(z - 0.25).toFixed(2)));
  const handleResetZoom = () => setZoom(1.0);

  // Compute bounding box coordinates
  // PyMuPDF rendered pages at 150 DPI, PDF points are at 72 DPI.
  // PDF pageWidth = naturalWidth / (150 / 72)
  const dpiRatio = 150 / 72; // ~2.0833
  const pdfPageWidth = naturalDims.width ? naturalDims.width / dpiRatio : 612;
  const pdfPageHeight = naturalDims.height ? naturalDims.height / dpiRatio : 792;

  let highlightStyle: React.CSSProperties | null = null;

  if (bbox && bbox.length === 4 && renderedDims.width > 0) {
    const [x0, y0, x1, y1] = bbox;
    // Scale factor from PDF points to currently rendered CSS pixels
    const scale = renderedDims.width / pdfPageWidth;

    const left = Math.max(0, x0 * scale);
    const top = Math.max(0, y0 * scale);
    const width = Math.max(8, (x1 - x0) * scale);
    const height = Math.max(8, (y1 - y0) * scale);

    highlightStyle = {
      position: "absolute",
      left: `${left}px`,
      top: `${top}px`,
      width: `${width}px`,
      height: `${height}px`,
    };
  }

  return (
    <div className="flex flex-col gap-2 w-full rounded-md border border-border bg-card/40 p-2.5">
      {/* Viewer toolbar */}
      <div className="flex items-center justify-between gap-2 border-b border-border/60 pb-2 text-xs">
        <div className="flex items-center gap-1.5 font-mono text-muted-foreground truncate">
          <FileText className="size-3.5 shrink-0 text-emerald-400" />
          <span className="truncate">
            Page {page} {filename ? `· ${filename}` : ""}
          </span>
        </div>

        <div className="flex items-center gap-1 shrink-0">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={handleZoomOut}
            disabled={zoom <= 0.6}
            className="size-7 p-0 text-muted-foreground hover:text-foreground"
            title="Zoom out"
          >
            <ZoomOut className="size-3.5" />
          </Button>
          <span className="min-w-[3rem] text-center font-mono text-[11px] text-muted-foreground">
            {Math.round(zoom * 100)}%
          </span>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={handleZoomIn}
            disabled={zoom >= 2.5}
            className="size-7 p-0 text-muted-foreground hover:text-foreground"
            title="Zoom in"
          >
            <ZoomIn className="size-3.5" />
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={handleResetZoom}
            className="size-7 p-0 text-muted-foreground hover:text-foreground"
            title="Reset zoom"
          >
            <RotateCcw className="size-3.5" />
          </Button>
        </div>
      </div>

      {/* Main Page Scroll Container */}
      <ScrollArea className="h-[360px] w-full rounded border border-border/40 bg-zinc-950/70 p-2">
        <div
          ref={containerRef}
          className="flex min-w-full justify-center"
          style={{
            transform: `scale(${zoom})`,
            transformOrigin: "top center",
            transition: "transform 0.15s ease-out",
          }}
        >
          <div className="relative inline-block shadow-lg">
            {/* Page image */}
            <img
              ref={imgRef}
              src={imgUrl}
              alt={`Evidence Page ${page}`}
              onLoad={handleImageLoad}
              onError={() => {
                setImgError(true);
                setImgLoaded(false);
              }}
              className={`max-w-full rounded transition-opacity duration-200 ${
                imgLoaded ? "opacity-100" : "opacity-0"
              }`}
              style={{ display: "block", width: "100%", maxHeight: "none" }}
            />

            {/* Bounding box overlay: 2px emerald border + 15% emerald fill */}
            {imgLoaded && highlightStyle && (
              <div
                style={highlightStyle}
                className="pointer-events-none rounded-[2px] border-2 border-emerald-400 bg-emerald-400/15 shadow-[0_0_12px_rgba(52,211,153,0.35)] transition-all"
              >
                <div className="absolute -top-5 left-0 rounded bg-emerald-500/90 px-1 py-0.5 text-[9px] font-medium tracking-tight text-zinc-950 shadow">
                  Grounding Evidence
                </div>
              </div>
            )}

            {/* Loading Skeleton */}
            {!imgLoaded && !imgError && (
              <div className="flex h-[320px] w-[260px] flex-col items-center justify-center gap-3 rounded bg-zinc-900/60 p-4 text-center">
                <div className="size-6 animate-spin rounded-full border-2 border-emerald-400 border-t-transparent" />
                <p className="text-xs text-muted-foreground">Loading page evidence...</p>
              </div>
            )}

            {/* Error fallback */}
            {imgError && (
              <div className="flex h-[300px] w-[260px] flex-col items-center justify-center gap-2 rounded border border-dashed border-border/70 p-4 text-center">
                <AlertCircle className="size-5 text-amber-400" />
                <p className="text-xs font-medium text-foreground">Page Render Unavailable</p>
                <p className="text-[11px] text-muted-foreground">
                  Document page image is still rendering or temporarily inaccessible.
                </p>
              </div>
            )}
          </div>
        </div>
      </ScrollArea>

      {/* Verbatim quote snippet below viewer */}
      {quote && (
        <div className="rounded bg-muted/40 px-2.5 py-1.5 text-[11px] text-muted-foreground border-l-2 border-emerald-500">
          <span className="font-semibold text-foreground/80">Matched text: </span>
          <span className="font-mono text-zinc-300">"{quote}"</span>
        </div>
      )}
    </div>
  );
}
