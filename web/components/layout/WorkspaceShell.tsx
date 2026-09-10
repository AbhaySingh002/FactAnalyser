"use client";

import React, { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { 
  FolderOpen, 
  ShieldCheck, 
  Layers, 
  MessageSquare,
  Menu,
  X,
  Plus,
  Trash2
} from "lucide-react";
import { UserButton } from "@/components/auth/AuthProvider";
import { useChatSession } from "@/components/chat/ChatSessionContext";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { href: "/app", label: "Documents", icon: FolderOpen },
  { href: "/app/audit", label: "Audit", icon: ShieldCheck },
  { href: "/app/cases", label: "Cases", icon: Layers },
  { href: "/app/chat", label: "Chat", icon: MessageSquare },
];

export function WorkspaceShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const { sessions, activeSessionId, setActiveSessionId, handleNewChat, handleDeleteSession } = useChatSession();

  const renderChatSessions = () => {
    if (!pathname.startsWith("/app/chat")) return null;
    return (
      <div className="mt-4 pt-3 border-t border-border/50 animate-in fade-in slide-in-from-top-1 duration-200">
        <div className="flex items-center justify-between px-2 mb-2">
          <span className="text-[10px] font-mono tracking-wider text-muted-foreground/80 uppercase font-semibold">
            Chat Sessions
          </span>
          <button
            type="button"
            onClick={handleNewChat}
            className="flex items-center gap-1 px-1.5 py-0.5 text-[11px] text-muted-foreground hover:text-foreground hover:bg-accent/60 rounded transition-colors"
            title="Start a new chat session"
          >
            <Plus className="size-3" />
            <span>New</span>
          </button>
        </div>
        <div className="space-y-0.5 max-h-[45vh] overflow-y-auto pr-1">
          {sessions.length === 0 ? (
            <div className="px-2 py-3 text-center text-xs text-muted-foreground/70">
              No active sessions
            </div>
          ) : (
            sessions.map((sess) => {
              const isActive = sess.id === activeSessionId;
              return (
                <div
                  key={sess.id}
                  onClick={() => {
                    setActiveSessionId(sess.id);
                    setMobileMenuOpen(false);
                  }}
                  className={cn(
                    "group relative flex items-center justify-between rounded-md px-2.5 py-1.5 text-xs cursor-pointer transition-colors",
                    isActive
                      ? "bg-accent text-accent-foreground font-medium shadow-xs"
                      : "text-muted-foreground hover:bg-muted/50 hover:text-foreground"
                  )}
                >
                  <div className="flex items-center gap-2 min-w-0 pr-1">
                    <MessageSquare className={cn("size-3.5 shrink-0", isActive ? "text-emerald-400" : "opacity-60")} />
                    <span className="truncate">{sess.title}</span>
                  </div>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDeleteSession(sess.id);
                    }}
                    className="opacity-0 group-hover:opacity-100 p-0.5 text-muted-foreground hover:text-rose-400 rounded transition-all"
                    title="Delete session"
                  >
                    <Trash2 className="size-3" />
                  </button>
                </div>
              );
            })
          )}
        </div>
      </div>
    );
  };

  return (
    <div className="flex h-[100dvh] w-full overflow-hidden bg-background">
      {/* Desktop Sidebar */}
      <aside className="hidden lg:flex w-[240px] flex-col border-r border-border bg-card/30 shrink-0">
        <div className="flex h-14 items-center px-4 border-b border-border">
          <Link href="/" className="flex items-center gap-2 group" title="Return to home">
            <div className="flex size-6 items-center justify-center rounded-sm bg-primary text-primary-foreground font-bold font-mono text-xs shadow-xs group-hover:scale-105 transition-transform">
              FC
            </div>
            <span className="font-bold tracking-tight text-foreground text-sm group-hover:text-primary transition-colors">FIN Cracker</span>
          </Link>
        </div>

        <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
          {NAV_ITEMS.map((item) => {
            const isActive = pathname === item.href || (item.href !== "/app" && pathname.startsWith(item.href));
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "relative flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-all",
                  isActive
                    ? "bg-accent text-accent-foreground font-semibold before:absolute before:left-0 before:top-2 before:bottom-2 before:w-1 before:bg-primary before:rounded-r-sm"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground active:scale-[0.99]"
                )}
              >
                <item.icon className={cn("size-4 shrink-0", isActive ? "text-primary" : "text-muted-foreground")} />
                {item.label}
              </Link>
            );
          })}
          {renderChatSessions()}
        </nav>

        <div className="p-3 border-t border-border mt-auto bg-card/40">
          <UserButton />
        </div>
      </aside>

      {/* Mobile Header & Sidebar */}
      <div className="lg:hidden fixed top-0 left-0 right-0 z-50 flex h-14 items-center justify-between border-b border-border bg-background/95 backdrop-blur px-4">
        <Link href="/" className="flex items-center gap-2 group" title="Return to home">
          <div className="flex size-6 items-center justify-center rounded-sm bg-primary text-primary-foreground font-bold font-mono text-xs group-hover:scale-105 transition-transform">
            FC
          </div>
          <span className="font-bold tracking-tight text-foreground text-sm group-hover:text-primary transition-colors">FIN Cracker</span>
        </Link>
        <button
          onClick={() => setMobileMenuOpen(true)}
          className="p-2 -mr-2 text-muted-foreground hover:text-foreground transition-colors"
          aria-label="Open menu"
        >
          <Menu className="size-5" />
        </button>
      </div>

      {mobileMenuOpen && (
        <div
          className="lg:hidden fixed inset-0 z-50 bg-background/80 backdrop-blur-sm animate-in fade-in duration-200"
          onClick={() => setMobileMenuOpen(false)}
        >
          <div
            className="fixed inset-y-0 right-0 w-[260px] border-l border-border bg-background shadow-2xl flex flex-col animate-in slide-in-from-right-full duration-200"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex h-14 items-center justify-between px-4 border-b border-border">
              <Link
                href="/"
                onClick={() => setMobileMenuOpen(false)}
                className="flex items-center gap-2 group"
                title="Return to home"
              >
                <div className="flex size-6 items-center justify-center rounded-sm bg-primary text-primary-foreground font-bold font-mono text-xs">
                  FC
                </div>
                <span className="font-bold tracking-tight text-foreground text-sm group-hover:text-primary transition-colors">FIN Cracker</span>
              </Link>
              <button
                onClick={() => setMobileMenuOpen(false)}
                className="p-1.5 text-muted-foreground hover:text-foreground rounded-md hover:bg-muted transition-colors"
                aria-label="Close menu"
              >
                <X className="size-4" />
              </button>
            </div>
            <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
              {NAV_ITEMS.map((item) => {
                const isActive = pathname === item.href || (item.href !== "/app" && pathname.startsWith(item.href));
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    onClick={() => setMobileMenuOpen(false)}
                    className={cn(
                      "relative flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                      isActive
                        ? "bg-accent text-accent-foreground font-semibold before:absolute before:left-0 before:top-2 before:bottom-2 before:w-1 before:bg-primary before:rounded-r-sm"
                        : "text-muted-foreground hover:text-foreground hover:bg-muted"
                    )}
                  >
                    <item.icon className="size-4 shrink-0" />
                    {item.label}
                  </Link>
                );
              })}
              {renderChatSessions()}
            </nav>
            <div className="p-3 border-t border-border mt-auto bg-card/40">
              <UserButton />
            </div>
          </div>
        </div>
      )}

      {/* Main Content Area */}
      <main className="flex-1 flex flex-col min-w-0 overflow-hidden lg:pt-0 pt-14 relative">
        <div className={cn("flex-1", pathname.startsWith("/app/chat") ? "h-full overflow-hidden" : "overflow-y-auto")}>
          {children}
        </div>
      </main>
    </div>
  );
}
