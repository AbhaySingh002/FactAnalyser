"use client";

import React, { useState, useRef, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import {
  Send,
  Bot,
  User,
  Sparkles,
  ShieldCheck,
  FileText,
  ArrowRight,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { Citation } from "@/lib/types";
import { EvidenceSheet } from "@/components/EvidenceSheet";
import { cn } from "@/lib/utils";

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  timestamp: string;
}

const SUGGESTED_QUESTIONS = [
  "What is the total reported revenue across filings, and are there any conflicts?",
  "Compare the net income figures reported across documents.",
  "Are there any discrepancies in EBITDA margins or reporting periods?",
];

export default function ChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);

  // Evidence Sheet State
  const [selectedFactId, setSelectedFactId] = useState<string | null>(null);
  const [sheetOpen, setSheetOpen] = useState(false);

  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, loading]);

  const handleCitationClick = (factId: string) => {
    setSelectedFactId(factId);
    setSheetOpen(true);
  };

  const handleSend = async (textToSend?: string) => {
    const query = (textToSend || input).trim();
    if (!query || loading) return;

    const userMessage: ChatMessage = {
      id: `user-${Date.now()}`,
      role: "user",
      content: query,
      timestamp: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setLoading(true);

    try {
      const historyPayload = messages.map((m) => ({
        role: m.role,
        content: m.content,
      }));

      const response = await api.sendChat(query, historyPayload);

      const botMessage: ChatMessage = {
        id: `assistant-${Date.now()}`,
        role: "assistant",
        content: response.answer,
        citations: response.citations,
        timestamp: new Date().toISOString(),
      };

      setMessages((prev) => [...prev, botMessage]);
    } catch (err: any) {
      const errorMessage: ChatMessage = {
        id: `err-${Date.now()}`,
        role: "assistant",
        content: `Error: ${err?.message || "Failed to contact chat intelligence layer."}`,
        timestamp: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setLoading(false);
      setTimeout(() => textareaRef.current?.focus(), 50);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // Render assistant content with clickable [F{id}] chips
  const renderMessageContent = (content: string) => {
    // Regex for citation tags: [F{uuid or id}]
    const parts = content.split(/(\[F[a-f0-9\-]+\])/gi);

    return (
      <div className="text-xs sm:text-sm leading-relaxed space-y-2">
        {parts.map((part, idx) => {
          const match = part.match(/^\[F([a-f0-9\-]+)\]$/i);
          if (match) {
            const factId = match[1];
            const shortId = factId.slice(0, 6);
            return (
              <Badge
                key={idx}
                variant="outline"
                onClick={() => handleCitationClick(factId)}
                className="mx-1 inline-flex items-center gap-1 font-mono text-[11px] font-semibold border-emerald-500/40 bg-emerald-500/10 text-emerald-400 cursor-pointer hover:bg-emerald-500/20 hover:border-emerald-400 transition-colors shadow-xs"
                title={`Open evidence for fact ${factId}`}
              >
                <span>[F:{shortId}]</span>
              </Badge>
            );
          }

          return (
            <span key={idx}>
              <ReactMarkdown
                components={{
                  p: ({ children }) => <span>{children}</span>,
                  ul: ({ children }) => <ul className="list-disc pl-4 space-y-1 my-1.5">{children}</ul>,
                  ol: ({ children }) => <ol className="list-decimal pl-4 space-y-1 my-1.5">{children}</ol>,
                  li: ({ children }) => <li>{children}</li>,
                  strong: ({ children }) => <strong className="font-semibold text-foreground">{children}</strong>,
                  code: ({ children }) => (
                    <code className="rounded bg-muted/60 px-1 py-0.5 font-mono text-[11px] text-foreground">
                      {children}
                    </code>
                  ),
                }}
              >
                {part}
              </ReactMarkdown>
            </span>
          );
        })}
      </div>
    );
  };

  return (
    <div className="flex flex-col h-[calc(100vh-8rem)] max-w-4xl mx-auto">
      {/* Chat header */}
      <div className="flex items-center justify-between border-b border-border/60 pb-3 mb-3">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-foreground flex items-center gap-2">
            <Sparkles className="size-4 text-emerald-400" />
            Grounded Due-Diligence Chat
          </h1>
          <p className="text-xs text-muted-foreground">
            Strict provenance RAG. Every claim is cited with clickable evidence coordinates.
          </p>
        </div>

        <Badge
          variant="outline"
          className="border-emerald-500/30 bg-emerald-500/10 text-emerald-400 text-[10px] font-mono flex items-center gap-1"
        >
          <ShieldCheck className="size-3" />
          Zero-Hallucination Refusal Active
        </Badge>
      </div>

      {/* Messages Scroll Area */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto pr-2 space-y-4 rounded-lg border border-border/60 bg-card/40 p-4"
      >
        {messages.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-center p-6 space-y-4 my-auto">
            <div className="flex size-12 items-center justify-center rounded-full bg-emerald-500/10 border border-emerald-500/30 text-emerald-400">
              <Bot className="size-6" />
            </div>

            <div className="space-y-1">
              <h3 className="text-base font-semibold text-foreground">
                Ask Questions Grounded in Financial Filings
              </h3>
              <p className="text-xs text-muted-foreground max-w-md">
                The engine checks pgvector embeddings + full-text claims. If no verified evidence supports an answer, it refuses deterministically.
              </p>
            </div>

            {/* Suggested questions */}
            <div className="w-full max-w-lg space-y-2 pt-2">
              <div className="text-[11px] font-mono text-muted-foreground uppercase text-left pl-1">
                Suggested Due-Diligence Prompts:
              </div>
              {SUGGESTED_QUESTIONS.map((q, idx) => (
                <button
                  key={idx}
                  onClick={() => handleSend(q)}
                  className="w-full text-left rounded-md border border-border/70 bg-muted/30 px-3.5 py-2.5 text-xs text-foreground/90 hover:bg-muted/70 hover:border-border transition-colors flex items-center justify-between group"
                >
                  <span className="truncate pr-2">{q}</span>
                  <ArrowRight className="size-3 text-muted-foreground group-hover:text-emerald-400 shrink-0 transition-colors" />
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((msg) => (
            <div
              key={msg.id}
              className={cn(
                "flex items-start gap-3 rounded-lg p-3.5 transition-colors",
                msg.role === "user"
                  ? "bg-muted/30 ml-8 border border-border/40"
                  : "bg-zinc-950/60 mr-8 border border-border/70"
              )}
            >
              <Avatar className="size-7 rounded-md border border-border/60 shrink-0 mt-0.5">
                <AvatarFallback
                  className={cn(
                    "text-xs font-mono font-bold",
                    msg.role === "user"
                      ? "bg-muted text-foreground"
                      : "bg-emerald-500/20 text-emerald-400"
                  )}
                >
                  {msg.role === "user" ? <User className="size-3.5" /> : <Bot className="size-3.5" />}
                </AvatarFallback>
              </Avatar>

              <div className="flex-1 space-y-1.5 overflow-hidden">
                <div className="flex items-center justify-between text-[11px] font-mono text-muted-foreground">
                  <span className="font-semibold text-foreground">
                    {msg.role === "user" ? "You" : "Grounded Engine"}
                  </span>
                  <span>{new Date(msg.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</span>
                </div>

                {renderMessageContent(msg.content)}

                {/* Citations chip bibliography */}
                {msg.citations && msg.citations.length > 0 && (
                  <div className="mt-3 pt-2.5 border-t border-border/50 space-y-1.5">
                    <span className="text-[10px] font-mono text-muted-foreground uppercase flex items-center gap-1">
                      <FileText className="size-3 text-emerald-400" />
                      Referenced Evidence ({msg.citations.length}):
                    </span>
                    <div className="flex flex-wrap gap-1.5">
                      {msg.citations.map((c, i) => (
                        <button
                          key={i}
                          onClick={() => handleCitationClick(c.fact_id)}
                          className="inline-flex items-center gap-1 rounded bg-muted/40 hover:bg-muted border border-border/60 px-2 py-1 text-[11px] font-mono text-foreground/80 hover:text-foreground transition-colors"
                        >
                          <span className="text-emerald-400 font-semibold">[F:{c.fact_id.slice(0, 6)}]</span>
                          {c.filename && <span className="truncate max-w-[120px]">{c.filename}</span>}
                          {c.page && <span className="text-muted-foreground">p.{c.page}</span>}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          ))
        )}

        {/* Loading skeleton while awaiting assistant response */}
        {loading && (
          <div className="flex items-start gap-3 rounded-lg bg-zinc-950/60 p-3.5 mr-8 border border-border/70">
            <Avatar className="size-7 rounded-md border border-border/60 shrink-0 bg-emerald-500/20 text-emerald-400">
              <AvatarFallback>
                <Bot className="size-3.5" />
              </AvatarFallback>
            </Avatar>
            <div className="flex-1 space-y-2 py-1">
              <Skeleton className="h-3.5 w-1/4" />
              <Skeleton className="h-3 w-3/4" />
              <Skeleton className="h-3 w-1/2" />
            </div>
          </div>
        )}
      </div>

      {/* Composer Input Bar */}
      <div className="mt-3 flex items-end gap-2 bg-card/60 p-2 rounded-lg border border-border/70">
        <Textarea
          ref={textareaRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask a due-diligence question across filings... (Enter to send, Shift+Enter for newline)"
          className="min-h-[44px] max-h-32 text-xs sm:text-sm bg-transparent border-0 focus-visible:ring-0 resize-none py-2 px-2"
          rows={1}
        />
        <Button
          size="sm"
          onClick={() => handleSend()}
          disabled={!input.trim() || loading}
          className="h-9 px-3 bg-emerald-500 text-zinc-950 hover:bg-emerald-400 font-semibold shrink-0"
        >
          <Send className="size-3.5 mr-1" />
          Send
        </Button>
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
