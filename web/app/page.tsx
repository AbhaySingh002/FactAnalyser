import Link from "next/link";
import {
  ArrowRight,
  FileSearch,
  GitCompare,
  Terminal,
  Cpu,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export default function LandingPage() {
  return (
    <div className="relative min-h-screen flex flex-col bg-background text-foreground overflow-x-hidden selection:bg-emerald-500/20 selection:text-emerald-200">
      {/* Background subtle grid */}
      <div className="absolute inset-0 bg-[radial-gradient(oklch(1_0_0/0.05)_1px,transparent_1px)] [background-size:24px_24px] pointer-events-none" />

      {/* Top navigation */}
      <header className="relative z-10 border-b border-border/70 bg-background/80 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-4 sm:px-6">
          <div className="flex items-center gap-2.5">
            <div className="flex size-7 items-center justify-center rounded bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 font-mono font-bold text-xs">
              FK
            </div>
            <span className="font-semibold text-sm tracking-tight">Fact Knowledge Layer</span>
          </div>

          <div className="flex items-center gap-3">
            <Link href="#architecture" className="text-xs text-muted-foreground hover:text-foreground transition-colors hidden sm:inline-block">
              Architecture
            </Link>
            <Link href="/app">
              <Button size="sm" className="h-8 px-3 text-xs bg-emerald-500 text-zinc-950 hover:bg-emerald-400 font-medium">
                Open Workspace
                <ArrowRight className="size-3.5 ml-1.5" />
              </Button>
            </Link>
          </div>
        </div>
      </header>

      {/* Hero Section */}
      <section className="relative z-10 pt-16 pb-14 md:pt-20 md:pb-18 px-4 sm:px-6 max-w-4xl mx-auto text-center flex flex-col items-center">
        <Badge
          variant="outline"
          className="mb-4 border-emerald-500/30 bg-emerald-500/10 text-emerald-400 text-[11px] font-mono tracking-wider uppercase px-2.5 py-0.5"
        >
          Institutional Due-Diligence Engine
        </Badge>

        <h1 className="text-4xl sm:text-5xl md:text-6xl font-extrabold tracking-tight text-foreground leading-[1.1] max-w-3xl">
          Every fact. Grounded. <br className="hidden sm:inline" />
          Every conflict. <span className="text-emerald-400">Explained.</span>
        </h1>

        <p className="mt-4 text-sm sm:text-base text-muted-foreground max-w-xl leading-relaxed">
          Extract financial claims from filings, link every number to its exact bounding box, and detect cross-document discrepancies deterministically.
        </p>

        <div className="mt-7 flex flex-wrap items-center justify-center gap-3">
          <Link href="/app">
            <Button size="lg" className="h-10 px-5 text-sm bg-emerald-500 text-zinc-950 hover:bg-emerald-400 font-semibold shadow-[0_0_20px_rgba(52,211,153,0.3)]">
              Open Workspace
              <ArrowRight className="size-4 ml-1.5" />
            </Button>
          </Link>
          <Link href="#architecture">
            <Button size="lg" variant="outline" className="h-10 px-5 text-sm border-border hover:bg-muted">
              View Architecture
            </Button>
          </Link>
        </div>
      </section>

      {/* 3-Step Pipeline Row */}
      <section className="relative z-10 py-12 px-4 sm:px-6 max-w-6xl mx-auto w-full">
        <div className="text-center mb-8">
          <h2 className="text-xl sm:text-2xl font-bold tracking-tight">
            Deterministic Precision at Every Layer
          </h2>
          <p className="text-xs sm:text-sm text-muted-foreground mt-1">
            Eliminating LLM hallucinations through strict spatial provenance and rule-based reconciliation.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
          {/* Step 1 */}
          <Card className="border-border/70 bg-card/60 backdrop-blur transition-all hover:border-emerald-500/40">
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between mb-1">
                <span className="font-mono text-xs font-semibold text-emerald-400">STAGE 01</span>
                <FileSearch className="size-4 text-muted-foreground" />
              </div>
              <CardTitle className="text-base font-semibold">Parse & Layout Fidelity</CardTitle>
            </CardHeader>
            <CardContent className="text-xs text-muted-foreground leading-relaxed">
              PyMuPDF column-aware chunking preserving reading order and table markdown. Automatic scan triage with dual OCR fallback (Groq llama-4-scout + Gemini) and page renders stored directly on Cloudflare R2.
            </CardContent>
          </Card>

          {/* Step 2 */}
          <Card className="border-border/70 bg-card/60 backdrop-blur transition-all hover:border-emerald-500/40">
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between mb-1">
                <span className="font-mono text-xs font-semibold text-emerald-400">STAGE 02</span>
                <Cpu className="size-4 text-muted-foreground" />
              </div>
              <CardTitle className="text-base font-semibold">Extract & Ground</CardTitle>
            </CardHeader>
            <CardContent className="text-xs text-muted-foreground leading-relaxed">
              Schema-constrained extraction with Groq llama-3.3-70b. Every extracted claim is bound to verbatim quotes and PDF bounding box coordinates with algorithmic fuzzy-quote verification.
            </CardContent>
          </Card>

          {/* Step 3 */}
          <Card className="border-border/70 bg-card/60 backdrop-blur transition-all hover:border-emerald-500/40">
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between mb-1">
                <span className="font-mono text-xs font-semibold text-emerald-400">STAGE 03</span>
                <GitCompare className="size-4 text-muted-foreground" />
              </div>
              <CardTitle className="text-base font-semibold">Reconcile & Verify</CardTitle>
            </CardHeader>
            <CardContent className="text-xs text-muted-foreground leading-relaxed">
              Deterministic rule engine (R1–R5) categorizing pairs into corroboration, direct numerical contradiction, or contextual variance. Powers grounded Q&A with strict zero-hallucination refusal.
            </CardContent>
          </Card>
        </div>
      </section>

      {/* Architecture Section */}
      <section id="architecture" className="relative z-10 py-12 px-4 sm:px-6 max-w-6xl mx-auto w-full">
        <Card className="border-border/80 bg-zinc-950/80 overflow-hidden shadow-2xl">
          <CardHeader className="border-b border-border/70 pb-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Terminal className="size-4 text-emerald-400" />
                <CardTitle className="text-sm font-semibold font-mono tracking-tight text-zinc-100">
                  SYSTEM_ARCHITECTURE.spec
                </CardTitle>
              </div>
              <Badge variant="outline" className="font-mono text-[10px] text-zinc-400 border-zinc-800">
                Stateless API + Managed Postgres
              </Badge>
            </div>
            <CardDescription className="text-xs text-zinc-400">
              End-to-end data pipeline from raw PDF ingestion to verified conversational matrix.
            </CardDescription>
          </CardHeader>
          <CardContent className="p-4 sm:p-6 overflow-x-auto">
            <pre className="font-mono text-xs leading-relaxed text-zinc-300 select-all">
{`┌──────────────────────────────────────────────────────────────────────────────────────────┐
│                             FACT KNOWLEDGE LAYER ARCHITECTURE                            │
└──────────────────────────────────────────────────────────────────────────────────────────┘

  [Uploaded PDFs] ──> (POST /documents)
           │
           ├──> [Storage: Cloudflare R2] (PDF bytes + 150 DPI page PNGs)
           │
           └──> [FastAPI Pipeline Worker]
                     │
                     ├─ Stage 1: PyMuPDF Parse (Column order, heading detection, tables)
                     ├─ Stage 2: Triage native text vs scan (char count threshold < 40)
                     ├─ Stage 3: Vision OCR (Groq llama-4-scout with Gemini Flash fallback)
                     ├─ Stage 4: Extract Claims (Groq llama-3.3-70b + verbatim quote validation)
                     ├─ Stage 5: Normalization (Scales, currencies, periods, entity aliases)
                     ├─ Stage 6: Semantic Embeddings (Gemini 768-dim into pgvector HNSW)
                     └─ Stage 7: Deterministic Pairwise Reconciliation (Rules R1-R5)
                                    │
                                    ├──> [Postgres + pgvector] (Single Source of Truth)
                                    │      ├─ facts (id, entity, attribute, bbox, quote, conf)
                                    │      ├─ fact_relations (corroborates / contradicts / variance)
                                    │      └─ audit (immutable execution lineage log)
                                    │
                                    ▼
       ┌────────────────────────────┴────────────────────────────┐
       │                                                         │
       ▼                                                         ▼
[Fact Matrix: /app/matrix]                                 [Grounded Chat: /app/chat]
 • Sticky entity rows × attribute headers                   • Fact-grounded citations [F{id}]
 • Worst-relation badges with tooltips                      • Zero-hallucination refusal guarantee
 • Click-to-source bounding box viewer                      • Clickable chips opening Evidence Sheet`}
            </pre>
          </CardContent>
        </Card>
      </section>

      {/* Footer */}
      <footer className="relative z-10 mt-auto border-t border-border/70 py-6 text-center text-xs text-muted-foreground">
        <div className="max-w-6xl mx-auto px-4 flex flex-col sm:flex-row items-center justify-between gap-3">
          <p>Superjoin Due-Diligence Fact Knowledge Layer Prototype</p>
          <p className="font-mono text-[11px]">
            FastAPI · Postgres + pgvector · Cloudflare R2 · Groq · Next.js 16
          </p>
        </div>
      </footer>
    </div>
  );
}
