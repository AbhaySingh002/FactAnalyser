"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  FileText,
  Table,
  MessageSquare,
  Network,
  CheckCircle2,
  ShieldAlert,
  Layers,
  Activity,
  ExternalLink,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { href: "/app", label: "Documents", icon: FileText },
  { href: "/app/matrix", label: "Fact Matrix", icon: Table },
  { href: "/app/chat", label: "Grounded Chat", icon: MessageSquare },
  { href: "/app/graph", label: "Knowledge Graph", icon: Network },
  { href: "/app/cases", label: "4-Case Showcase", icon: Layers },
];

export function Navbar() {
  const pathname = usePathname();
  const [isBackendHealthy, setIsBackendHealthy] = useState<boolean | null>(null);

  useEffect(() => {
    let mounted = true;
    const check = async () => {
      const ok = await api.health();
      if (mounted) setIsBackendHealthy(ok);
    };
    check();
    const interval = setInterval(check, 15000);
    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, []);

  return (
    <header className="sticky top-0 z-40 w-full border-b border-border/80 bg-background/95 backdrop-blur supports-backdrop-filter:bg-background/80">
      <div className="mx-auto flex h-14 max-w-7xl items-center justify-between px-4 sm:px-6">
        {/* Brand & Workspace name */}
        <div className="flex items-center gap-6">
          <Link href="/" className="flex items-center gap-2.5 transition-opacity hover:opacity-90">
            <div className="flex size-7 items-center justify-center rounded-md bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 font-mono font-bold text-xs">
              FK
            </div>
            <div className="flex flex-col leading-none">
              <span className="text-sm font-semibold tracking-tight text-foreground flex items-center gap-1.5">
                Fact Knowledge Layer
                <Badge variant="outline" className="font-mono text-[9px] px-1 py-0 text-muted-foreground border-border/60">
                  v1.0
                </Badge>
              </span>
              <span className="text-[10px] text-muted-foreground font-mono">
                Due-Diligence Reconciliation
              </span>
            </div>
          </Link>

          {/* Nav links */}
          <nav className="hidden md:flex items-center gap-1">
            {NAV_ITEMS.map((item) => {
              const Icon = item.icon;
              const isActive =
                item.href === "/app"
                  ? pathname === "/app"
                  : pathname.startsWith(item.href);

              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    "flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium transition-colors",
                    isActive
                      ? "bg-accent text-foreground shadow-xs font-semibold"
                      : "text-muted-foreground hover:bg-accent/50 hover:text-foreground"
                  )}
                >
                  <Icon className={cn("size-3.5", isActive ? "text-emerald-400" : "text-muted-foreground")} />
                  <span>{item.label}</span>
                </Link>
              );
            })}
          </nav>
        </div>

        {/* System telemetry & actions */}
        <div className="flex items-center gap-2">
          {/* Health indicator badge */}
          <div
            className="flex items-center gap-1.5 rounded-full border border-border/60 bg-muted/40 px-2.5 py-1 text-[11px] font-mono"
            title={
              isBackendHealthy === null
                ? "Checking backend connectivity..."
                : isBackendHealthy
                ? "Backend is online and responsive"
                : "Backend is warming up (cold start can take up to 60s)"
            }
          >
            <span
              className={cn(
                "size-1.5 rounded-full",
                isBackendHealthy === null
                  ? "bg-zinc-400 animate-pulse"
                  : isBackendHealthy
                  ? "bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.8)]"
                  : "bg-amber-400 animate-pulse"
              )}
            />
            <span className="text-muted-foreground">
              {isBackendHealthy === null
                ? "Connecting..."
                : isBackendHealthy
                ? "Engine Ready"
                : "Waking Engine"}
            </span>
          </div>

          <Link href="/">
            <Button variant="ghost" size="sm" className="h-8 px-2.5 text-xs text-muted-foreground hover:text-foreground">
              Overview
            </Button>
          </Link>
        </div>
      </div>
    </header>
  );
}
