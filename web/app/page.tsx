"use client";

import React, { useState } from "react";
import Link from "next/link";
import { motion, useReducedMotion } from "motion/react";
import {
  ArrowRight,
  Shield,
  FileText,
  FileSpreadsheet,
  AlertTriangle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { SignedIn, SignedOut, UserButton } from "@/components/auth/AuthProvider";

// Showcase 3 core due diligence cases (single canonical source)
const CASE_STUDIES = [
  {
    id: "leases",
    sector: "Logistics",
    company: "National Freight Logistics",
    filings: "Audited FY24 Statutory Report vs Q4 Deck",
    lineItem: "Adjusted EBITDA vs Operating Cash Flow",
    statutoryReality: "₹423 Cr statutory cash from ops",
    reportedClaim: "₹461 Cr reported (5.7% margin)",
    variance: "₹38 Cr excluded lease liability (8.2% divergence)",
    riskLevel: "High Risk",
    finding:
      "Management presentation excluded ₹38 Cr in short-term rolling lease commitments disclosed only in Note 28.4 of the statutory accounts.",
    provenance: "Page 42, Note 28.4",
    bbox: { x: 80, y: 310, w: 450, h: 50, page: 42 },
    excerpt:
      "Note 28.4: Lease commitments under rolling short-term arrangements totaling ₹3,800 lakhs have been recorded under contractual operational outlays and excluded from non-GAAP lease amortization.",
  },
  {
    id: "capitalization",
    sector: "Enterprise Software",
    company: "CloudCore Systems",
    filings: "Form 10-K vs Series C Diligence Room",
    lineItem: "Capitalized R&D vs Cost of Delivery",
    statutoryReality: "Real Operating Margin 61.2%",
    reportedClaim: "Gross Margin 78.4%",
    variance: "$14.2M internal engineering costs capitalized",
    riskLevel: "High Risk",
    finding:
      "Internal developer compensation capitalized under software intangibles to artificially depress COGS and inflate gross margins prior to financing.",
    provenance: "Page 67, Schedule IV",
    bbox: { x: 110, y: 540, w: 420, h: 45, page: 67 },
    excerpt:
      "Schedule IV: During FY24, the Group capitalized internal software engineering expenditures of $14.2M as proprietary core IP, reducing direct cost of delivery.",
  },
  {
    id: "receivables",
    sector: "Chemicals",
    company: "Apex BioChemicals",
    filings: "Statutory Balance Sheet vs Audit Committee Memo",
    lineItem: "Trade Receivables Aging Schedule",
    statutoryReality: "Related-party receivables +104% YoY",
    reportedClaim: "Disclosed Revenue Growth +24.6%",
    variance: "₹89 Cr uncollected past 270 days",
    riskLevel: "Critical Flag",
    finding:
      "68% of incremental fourth-quarter revenue originated from an undisclosed affiliated distributor on non-standard 270-day payment terms.",
    provenance: "Page 108, Schedule XII",
    bbox: { x: 95, y: 215, w: 480, h: 60, page: 108 },
    excerpt:
      "Schedule XII: Trade receivables outstanding from Apex Global Distribution Ltd (common directorate) stood at ₹8,920 lakhs against credit terms exceeding 270 days.",
  },
];

// 3 clear steps (how it works)
const CORE_PILLARS = [
  {
    number: "01",
    title: "Upload company files",
    desc: "Add 10-Ks, investor presentations, statutory audit reports, or scanned financial notes in any standard format.",
    tag: "Input",
  },
  {
    number: "02",
    title: "Compare claims to filings",
    desc: "Check what pitch decks and earnings calls report against what was signed off by independent auditors.",
    tag: "Comparison",
  },
  {
    number: "03",
    title: "Click through to the source",
    desc: "Every extracted number highlights the exact table, footnote, and paragraph on the original PDF page.",
    tag: "Audit trail",
  },
];

// Common questions
const METHODOLOGY_FAQS = [
  {
    id: "faq-1",
    question: "How do you ensure extracted figures are reliable?",
    answer:
      "Every metric links directly to its source PDF. When you click a figure, the platform displays the exact footnote or table on that page, so your team can verify the math.",
  },
  {
    id: "faq-2",
    question: "Are uploads private?",
    answer:
      "Yes. Your uploads are only visible within your workspace.",
  },
  {
    id: "faq-3",
    question: "What types of files can I upload?",
    answer:
      "You can upload SEC filings (10-K, 10-Q), annual statutory reports (US GAAP, IFRS, MCA India), pitch decks, bank covenants, and scanned balance sheet schedules.",
  },
];

export default function LandingPage() {
  const [activeCaseIndex, setActiveCaseIndex] = useState(0);
  const shouldReduceMotion = useReducedMotion();
  const activeCase = CASE_STUDIES[activeCaseIndex];

  return (
    <div className="min-h-[100dvh] flex flex-col bg-background text-foreground font-sans antialiased">
      {/* ─── 1. Clean, Minimal Single-Line Navigation ─── */}
      <motion.header
        initial={shouldReduceMotion ? false : { y: -8, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ duration: 0.4 }}
        className="sticky top-4 z-40 max-w-5xl mx-auto px-4 w-full"
      >
        <div className="rounded-full border border-border/80 bg-background/90 backdrop-blur-md px-4 sm:px-5 py-2.5 shadow-xs flex items-center justify-between">
          {/* Logo */}
          <Link href="/" className="flex items-center gap-2.5">
            <div className="flex size-7 items-center justify-center rounded-md bg-primary text-primary-foreground text-xs font-semibold tracking-tight">
              FC
            </div>
            <span className="text-sm font-semibold tracking-tight text-foreground">
              FIN Cracker
            </span>
          </Link>

          {/* Minimal Links */}
          <nav className="hidden sm:flex items-center gap-6 text-xs text-muted-foreground font-medium">
            <a href="#preview" className="hover:text-foreground transition-colors">
              Comparison
            </a>
            <a href="#how-it-works" className="hover:text-foreground transition-colors">
              How it works
            </a>
            <a href="#methodology" className="hover:text-foreground transition-colors">
              Methodology
            </a>
          </nav>

          {/* Action */}
          <div className="flex items-center gap-2">
            <SignedIn>
              <Link href="/app/audit">
                <Button size="sm" variant="ghost" className="h-8 text-xs font-medium cursor-pointer">
                  Audit
                </Button>
              </Link>
              <UserButton />
            </SignedIn>

            <SignedOut>
              <Link href="/sign-in">
                <Button size="sm">
                  Sign in
                </Button>
              </Link>
            </SignedOut>
          </div>
        </div>
      </motion.header>

      {/* ─── 2. Hero: Clean, Direct, Restrained ─── */}
      <motion.section
        initial={shouldReduceMotion ? false : { opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        className="pt-16 pb-14 md:pt-20 md:pb-16 px-4 sm:px-6 max-w-4xl mx-auto w-full flex flex-col items-center text-center"
      >
        {/* Eyebrow */}
        <div className="inline-flex items-center gap-2 rounded-full border border-border bg-card px-3 py-1 text-[11px] font-medium text-muted-foreground mb-6">
          <Shield className="size-3 text-emerald-600 dark:text-emerald-400" />
          <span>Financial Document Analysis</span>
        </div>

        {/* Headline: Strict 2-line max */}
        <h1 className="text-4xl sm:text-5xl md:text-6xl font-semibold tracking-tight text-foreground max-w-2xl leading-[1.1] mb-4">
          Find what the numbers don&apos;t tell you.
        </h1>

        {/* Subtitle: Crisp & under 20 words */}
        <p className="text-base sm:text-lg text-muted-foreground max-w-lg leading-relaxed mb-8">
          Compare filings, trace footnote coordinates, and find discrepancies.
        </p>

        {/* Primary CTA Button */}
        <div className="flex items-center justify-center gap-3 mb-12">
          <Link href="/app/audit">
            <Button size="lg">
              <span>Start audit</span>
              <ArrowRight className="size-3.5 ml-2" />
            </Button>
          </Link>
        </div>

        {/* ─── Centerpiece: Comparison Session Split View ─── */}
        <div id="preview" className="w-full rounded-2xl border border-border bg-muted/40 p-2 sm:p-2.5 shadow-lg text-left">
          <div className="rounded-xl border border-border/80 bg-card overflow-hidden">
            {/* Window Top Bar with Case Selector */}
            <div className="px-4 py-3 border-b border-border flex flex-wrap items-center justify-between gap-3 text-xs bg-muted/20">
              <div className="flex items-center gap-2">
                <span className="size-2 rounded-full bg-emerald-500" />
                <span className="font-semibold text-foreground">
                  Example finding &middot; {activeCase.company}
                </span>
                <span className="text-[11px] text-muted-foreground hidden sm:inline font-mono">
                  ({activeCase.sector})
                </span>
              </div>

              {/* Case switcher tabs */}
              <div className="flex items-center gap-1 p-0.5 rounded-lg border border-border bg-muted/50 text-[11px]">
                {CASE_STUDIES.map((item, idx) => (
                  <button
                    key={item.id}
                    onClick={() => setActiveCaseIndex(idx)}
                    className={`px-2.5 py-1 rounded font-medium transition-all cursor-pointer ${
                      activeCaseIndex === idx
                        ? "bg-background text-foreground font-semibold shadow-xs"
                        : "text-muted-foreground hover:text-foreground"
                    }`}
                  >
                    {item.company.split(" ")[0]}
                  </button>
                ))}
              </div>
            </div>

            {/* Split Comparison Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 divide-y md:divide-y-0 md:divide-x divide-border text-xs">
              {/* Statutory Reality Column */}
              <div className="p-5 sm:p-6 space-y-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <FileText className="size-4 text-emerald-600 dark:text-emerald-400" />
                    <span className="font-semibold text-foreground uppercase tracking-wider text-[11px]">
                      Audited Statutory Accounts
                    </span>
                  </div>
                  <Badge variant="outline" className="text-[10px] font-mono border-emerald-500/30 text-emerald-600 dark:text-emerald-400 bg-emerald-500/5">
                    Source available
                  </Badge>
                </div>

                <div className="p-3 rounded-lg bg-muted/40 border border-border/60 space-y-1">
                  <div className="text-muted-foreground text-[11px]">Statutory Reality</div>
                  <div className="font-mono text-emerald-600 dark:text-emerald-400 font-bold text-sm">
                    {activeCase.statutoryReality}
                  </div>
                </div>

                <div className="p-3 rounded-lg bg-muted/20 border border-border/50 space-y-2">
                  <div className="flex items-center justify-between text-[11px] text-muted-foreground font-mono">
                    <span>Source Excerpt</span>
                    <span className="text-emerald-600 dark:text-emerald-400 font-semibold">{activeCase.provenance}</span>
                  </div>
                  <p className="text-foreground leading-relaxed italic text-[11px]">
                    &ldquo;{activeCase.excerpt}&rdquo;
                  </p>
                  <div className="pt-1.5 border-t border-border/40 flex items-center justify-between text-[10px] font-mono text-muted-foreground">
                    <TooltipProvider delay={100}>
                      <Tooltip>
                        <TooltipTrigger render={<span className="cursor-help underline decoration-dotted decoration-muted-foreground/50" />}>
                          BBox: [{activeCase.bbox.x}, {activeCase.bbox.y}, {activeCase.bbox.w}, {activeCase.bbox.h}]
                        </TooltipTrigger>
                        <TooltipContent side="top" className="text-[10px] font-mono">
                          Deterministic sub-millimeter PDF coordinates
                        </TooltipContent>
                      </Tooltip>
                    </TooltipProvider>
                    <span>Page {activeCase.bbox.page} Target</span>
                  </div>
                </div>
              </div>

              {/* Promotional Deck Column */}
              <div className="p-5 sm:p-6 space-y-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <FileSpreadsheet className="size-4 text-rose-500" />
                    <span className="font-semibold text-foreground uppercase tracking-wider text-[11px]">
                      Presentation Claim
                    </span>
                  </div>
                  <Badge variant="outline" className="text-[10px] font-mono border-rose-500/30 text-rose-600 dark:text-rose-400 bg-rose-500/5">
                    Variance Flagged
                  </Badge>
                </div>

                <div className="p-3 rounded-lg bg-rose-50/30 dark:bg-rose-950/20 border border-rose-200/60 dark:border-rose-900/50 space-y-1">
                  <div className="text-muted-foreground text-[11px]">Disclosed Metric</div>
                  <div className="font-mono text-rose-600 dark:text-rose-400 font-bold text-sm">
                    {activeCase.reportedClaim}
                  </div>
                </div>

                <div className="p-3 rounded-lg bg-rose-50/20 dark:bg-rose-950/10 border border-rose-200/40 dark:border-rose-900/40 space-y-1.5">
                  <div className="flex items-center gap-1.5 text-rose-700 dark:text-rose-400 font-semibold text-[11px]">
                    <AlertTriangle className="size-3.5" />
                    <span>Discrepancy Note</span>
                  </div>
                  <p className="text-muted-foreground text-[11px] leading-relaxed">
                    {activeCase.finding}
                  </p>
                  <div className="pt-1.5 border-t border-rose-200/30 dark:border-rose-900/30 flex items-center justify-between text-[10px] font-mono text-rose-600 dark:text-rose-400 font-bold">
                    <span>Variance:</span>
                    <span>{activeCase.variance}</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Comparison Footer Bar */}
            <div className="px-4 sm:px-6 py-2.5 border-t border-border bg-muted/30 flex items-center justify-between text-xs">
              <span className="text-[11px] text-muted-foreground font-mono">
                Check: <strong className="text-foreground font-medium font-sans">Operating cash flow vs EBITDA</strong>
              </span>
              <Link href="/app/audit">
                <Button size="sm" variant="ghost" className="h-6 text-xs text-foreground hover:bg-muted cursor-pointer">
                  Inspect in Audit &rarr;
                </Button>
              </Link>
            </div>
          </div>
        </div>
      </motion.section>

      {/* ─── 3. Clean 3-Pillar Architecture (How It Works) ─── */}
      <section id="how-it-works" className="py-16 md:py-20 px-4 sm:px-6 max-w-4xl mx-auto w-full border-t border-border">
        <div className="mb-10 text-left">
          <h2 className="text-2xl sm:text-3xl font-semibold tracking-tight text-foreground mb-2">
            How it works
          </h2>
          <p className="text-xs sm:text-sm text-muted-foreground max-w-xl leading-relaxed">
            See how pitch deck claims compare with filed statutory accounts.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-5 text-left">
          {CORE_PILLARS.map((p) => (
            <motion.div
              key={p.number}
              initial={shouldReduceMotion ? false : { opacity: 0, y: 12 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, amount: 0.2 }}
              transition={{ duration: 0.4 }}
              className="rounded-xl border border-border bg-card p-5 flex flex-col justify-between space-y-4 hover:border-border/80 transition-colors"
            >
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="font-mono text-xs text-muted-foreground">
                    Phase {p.number}
                  </span>
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-muted text-muted-foreground border border-border/60">
                    {p.tag}
                  </span>
                </div>
                <h3 className="text-base font-semibold text-foreground tracking-tight">
                  {p.title}
                </h3>
                <p className="text-xs text-muted-foreground leading-relaxed">
                  {p.desc}
                </p>
              </div>
            </motion.div>
          ))}
        </div>
      </section>

      {/* ─── 4. Methodology & Institutional Trust (FAQ) ─── */}
      <section id="methodology" className="py-16 md:py-20 px-4 sm:px-6 max-w-4xl mx-auto w-full border-t border-border">
        <div className="mb-10 text-left">
          <h2 className="text-2xl sm:text-3xl font-semibold tracking-tight text-foreground mb-2">
            Frequently asked questions
          </h2>
          <p className="text-xs sm:text-sm text-muted-foreground max-w-lg leading-relaxed">
            Clear answers on data privacy, accuracy, and supported documents.
          </p>
        </div>

        {/* Clean Accordion */}
        <Accordion defaultValue={["faq-1"]} className="w-full text-left space-y-2">
          {METHODOLOGY_FAQS.map((faq) => (
            <AccordionItem
              key={faq.id}
              value={faq.id}
              className="border-b border-border py-1.5"
            >
              <AccordionTrigger className="text-sm font-medium text-foreground hover:no-underline hover:text-emerald-600 dark:hover:text-emerald-400 transition-colors">
                {faq.question}
              </AccordionTrigger>
              <AccordionContent className="text-xs text-muted-foreground leading-relaxed pt-1.5">
                {faq.answer}
              </AccordionContent>
            </AccordionItem>
          ))}
        </Accordion>
      </section>

      {/* ─── 5. Minimal High-Conviction CTA ─── */}
      <section className="py-16 md:py-20 px-4 sm:px-6 max-w-3xl mx-auto w-full text-center">
        <div className="rounded-2xl border border-border bg-card p-8 sm:p-10 space-y-5 shadow-xs">
          <h2 className="text-2xl font-semibold tracking-tight text-foreground">
            Upload documents and begin.
          </h2>
          <p className="text-xs sm:text-sm text-muted-foreground max-w-md mx-auto leading-relaxed">
            Upload filings for any company and review side-by-side audit notes.
          </p>
          <div className="pt-2">
            <Link href="/app/audit">
              <Button size="lg">
                <span>Open Audit</span>
                <ArrowRight className="size-3.5 ml-2" />
              </Button>
            </Link>
          </div>
        </div>
      </section>

      {/* ─── 6. Clean Minimal Footer ─── */}
      <footer className="border-t border-border py-8 px-4 sm:px-6 max-w-5xl mx-auto w-full text-xs text-muted-foreground flex flex-col sm:flex-row items-center justify-between gap-4">
        <div className="flex items-center gap-2.5">
          <div className="flex size-5 items-center justify-center rounded bg-primary text-primary-foreground text-[10px] font-bold">
            FC
          </div>
          <span>FIN Cracker &middot; Due Diligence</span>
        </div>

        <div className="flex items-center gap-5">
          <Link href="/app/audit" className="hover:text-foreground transition-colors">
            Audit
          </Link>
          <Link href="/app/chat" className="hover:text-foreground transition-colors">
            Chat
          </Link>
          <Link href="/app/cases" className="hover:text-foreground transition-colors">
            Cases
          </Link>
          <Link href="/app" className="hover:text-foreground transition-colors">
            Documents
          </Link>
        </div>
      </footer>
    </div>
  );
}
