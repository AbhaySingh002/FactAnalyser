"use client";

import React, { useState, useRef, useEffect, useMemo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  Compass,
  Copy,
  Check,
  RotateCcw,
  FileText,
  ShieldCheck,
  Globe,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { Citation } from "@/lib/types";
import {
  ResearchBlock,
  ResearchStep,
  ResearchArtifact,
} from "@/lib/research-protocol";
import { useChatSession } from "@/components/chat/ChatSessionContext";
import { ChatComposer } from "@/components/chat/ChatComposer";
import { ResearchProgress } from "@/components/research/ResearchProgress";
import { ResearchBlockRenderer } from "@/components/research/ResearchBlockRenderer";
import { ResearchSidebar } from "@/components/research/ResearchSidebar";
import { EvidenceSheet } from "@/components/EvidenceSheet";
import { cn } from "@/lib/utils";

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  timestamp: string;
  researchSteps?: ResearchStep[];
  isResearching?: boolean;
  isStreaming?: boolean;
  blocks?: ResearchBlock[];
  artifacts?: ResearchArtifact[];
}

function CitationBadge({
  token,
  citations,
  onOpenEvidence,
}: {
  token: string;
  citations?: Citation[];
  onOpenEvidence: (factId: string) => void;
}) {
  const isWeb = token.startsWith("[W");
  const rawId = token.replace(/[\[\]]/g, "");

  if (isWeb) {
    const webIdx = rawId.replace("W", "");
    return (
      <span className="inline-flex items-center align-baseline mx-0.5">
        <Tooltip>
          <TooltipTrigger
            render={
              <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-mono font-medium border border-sky-500/30 bg-sky-500/10 text-sky-400 hover:bg-sky-500/20 transition-all cursor-help shadow-xs" />
            }
          >
            <Globe className="size-2.5" />
            <span>W{webIdx}</span>
          </TooltipTrigger>
          <TooltipContent
            side="top"
            className="w-64 border border-border/80 bg-card/95 text-foreground p-2.5 rounded-lg shadow-xl backdrop-blur-md space-y-1 z-50 text-left"
          >
            <div className="flex items-center gap-1.5 text-xs font-semibold text-sky-400">
              <Globe className="size-3" />
              <span>External Web Reference</span>
            </div>
            <p className="text-[11px] text-muted-foreground leading-relaxed">
              Synthesized from external financial search indices and regulatory filings.
            </p>
          </TooltipContent>
        </Tooltip>
      </span>
    );
  }

  // Internal fact citation
  const cleanToken = rawId.replace(/^F:?/i, "");
  const citation = citations?.find(
    (c) =>
      String(c.index) === cleanToken ||
      c.fact_id === cleanToken ||
      (cleanToken.length >= 6 && c.fact_id.startsWith(cleanToken))
  );

  const displayNum = citation?.index
    ? String(citation.index)
    : cleanToken.length > 8
    ? cleanToken.slice(0, 6)
    : cleanToken;
  const factIdToOpen = citation?.fact_id || cleanToken;

  return (
    <span className="inline-flex items-center align-baseline mx-0.5">
      <Tooltip>
        <TooltipTrigger
          render={
            <button
              type="button"
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
                onOpenEvidence(factIdToOpen);
              }}
              className="group inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-mono font-semibold border border-emerald-500/30 bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 hover:border-emerald-500/60 transition-all cursor-pointer shadow-xs active:scale-95 align-middle"
              title={`Inspect citation [${displayNum}] in source document`}
            />
          }
        >
          <span className="size-1 rounded-full bg-emerald-400 group-hover:scale-125 transition-transform" />
          <span>[{displayNum}]</span>
        </TooltipTrigger>
        <TooltipContent
          side="top"
          align="start"
          className="w-72 max-w-sm border border-border/90 bg-card/98 text-foreground p-3 rounded-xl shadow-2xl backdrop-blur-md space-y-2 z-50 text-left"
        >
          {/* Header */}
          <div className="flex items-center justify-between gap-2 border-b border-border/60 pb-1.5">
            <div className="flex items-center gap-1.5 min-w-0">
              <FileText className="size-3.5 text-emerald-400 shrink-0" />
              <span className="text-xs font-semibold truncate text-foreground">
                {citation?.filename || "Primary Filing Source"}
              </span>
            </div>
            {citation?.page !== undefined && (
              <Badge variant="outline" className="text-[10px] font-mono px-1 py-0 h-4 border-border shrink-0">
                p.{citation.page + 1}
              </Badge>
            )}
          </div>

          {/* Metric / assertion */}
          {citation?.entity && (
            <div className="text-[11px] font-medium text-foreground/90 flex items-center justify-between">
              <span className="truncate pr-2">
                {citation.entity} {citation.attribute && `· ${citation.attribute}`}
              </span>
              {citation.raw_value && (
                <span className="font-mono text-emerald-400 font-semibold shrink-0">
                  {citation.raw_value}
                </span>
              )}
            </div>
          )}

          {/* Quote excerpt */}
          {citation?.quote ? (
            <p className="text-[11px] text-muted-foreground italic line-clamp-3 leading-relaxed border-l-2 border-emerald-500/40 pl-2">
              &ldquo;{citation.quote}&rdquo;
            </p>
          ) : (
            <p className="text-[11px] text-muted-foreground">
              Direct primary evidence linked to this verified statement.
            </p>
          )}

          {/* Footer with action prompt */}
          <div className="flex items-center justify-between pt-1 border-t border-border/50 text-[10px] text-muted-foreground font-mono">
            <span className="flex items-center gap-1 text-emerald-400">
              <ShieldCheck className="size-3" />
              {citation?.confidence
                ? `${Math.round(citation.confidence * 100)}% verified`
                : "Audited fact"}
            </span>
            <span className="text-[9px] text-muted-foreground/80 hover:text-foreground">
              Click to view PDF bbox &rarr;
            </span>
          </div>
        </TooltipContent>
      </Tooltip>
    </span>
  );
}

export default function ChatPage() {
  const { activeSessionId, setSessions } = useChatSession();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const abortControllerRef = useRef<AbortController | null>(null);

  // Sidebars visibility
  const [rightSidebarOpen, setRightSidebarOpen] = useState(false);

  useEffect(() => {
    if (typeof window !== "undefined" && window.innerWidth >= 1024) {
      setRightSidebarOpen(true);
    }
  }, []);

  // Evidence Sheet State
  const [selectedFactId, setSelectedFactId] = useState<string | null>(null);
  const [sheetOpen, setSheetOpen] = useState(false);

  // Copy message state
  const [copiedMessageId, setCopiedMessageId] = useState<string | null>(null);

  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const userScrolledUpRef = useRef(false);

  // Auto-scroll handler preserving reading position if user scrolled up
  useEffect(() => {
    if (!userScrolledUpRef.current && messagesContainerRef.current) {
      messagesContainerRef.current.scrollTo({
        top: messagesContainerRef.current.scrollHeight,
        behavior: "smooth",
      });
    }
  }, [messages, loading]);

  // Load messages from localStorage when activeSessionId changes
  useEffect(() => {
    if (!activeSessionId) return;
    try {
      const stored = localStorage.getItem(`fincracker_chat_${activeSessionId}`);
      if (stored) {
        const parsed = JSON.parse(stored);
        if (Array.isArray(parsed)) {
          setMessages(
            parsed.map((m: ChatMessage) => ({
              ...m,
              isStreaming: false,
              isResearching: false,
            }))
          );
          userScrolledUpRef.current = false;
          return;
        }
      }
    } catch (e) {
      console.warn("Failed to load chat session from localStorage", e);
    }
    setMessages([]);
    userScrolledUpRef.current = false;
  }, [activeSessionId]);

  // Persist messages to localStorage on updates (debounced)
  useEffect(() => {
    if (!activeSessionId || messages.length === 0) return;
    const timer = setTimeout(() => {
      try {
        localStorage.setItem(
          `fincracker_chat_${activeSessionId}`,
          JSON.stringify(messages)
        );
      } catch (e) {
        console.warn("Failed to save chat session to localStorage", e);
      }
    }, 400);
    return () => clearTimeout(timer);
  }, [activeSessionId, messages]);

  const handleScroll = () => {
    if (!messagesContainerRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = messagesContainerRef.current;
    // If user is within 120px of bottom, consider them at bottom
    const isNearBottom = scrollHeight - (scrollTop + clientHeight) < 120;
    userScrolledUpRef.current = !isNearBottom;
  };

  const handleCitationClick = (factId: string) => {
    setSelectedFactId(factId);
    setSheetOpen(true);
  };

  // Navigate to block from right insights sidebar
  const handleNavigateToBlock = (blockId: string) => {
    const el = document.getElementById(blockId);
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "center" });
      el.classList.add("ring-2", "ring-emerald-400/80", "ring-offset-2");
      setTimeout(() => {
        el.classList.remove("ring-2", "ring-emerald-400/80", "ring-offset-2");
      }, 2000);
    }
  };

  // Collect all artifacts from recent messages for the secondary sidebar (top 2 will be surfaced)
  const currentArtifacts = useMemo(() => {
    const arts: ResearchArtifact[] = [];
    // traverse from most recent assistant message backwards
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].artifacts) {
        arts.push(...(messages[i].artifacts || []));
      }
    }
    return arts;
  }, [messages]);

  const currentBlocks = useMemo(() => {
    const blks: ResearchBlock[] = [];
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].blocks) {
        blks.push(...(messages[i].blocks || []));
      }
    }
    return blks;
  }, [messages]);


  const handleUploadFile = async (file: File) => {
    try {
      toast.info(`Uploading ${file.name}...`);
      const resp = await api.uploadDocument(file);
      toast.success(`Document uploaded: ${file.name}. Processing background extraction.`);
    } catch (err: any) {
      toast.error(err?.message || "Failed to upload document");
    }
  };

  const handleCopyMessage = (id: string, text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedMessageId(id);
    toast.success("Response copied to clipboard");
    setTimeout(() => setCopiedMessageId(null), 2000);
  };

  // Primary send handler supporting multi-step deep research and standard RAG
  const handleSend = async (
    textToSend: string,
    options?: { deepResearch?: boolean; webSearch?: boolean }
  ) => {
    const query = textToSend.trim();
    if (!query || loading) return;

    const userMessage: ChatMessage = {
      id: `user-${Date.now()}`,
      role: "user",
      content: query,
      timestamp: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setLoading(true);
    userScrolledUpRef.current = false;

    // Update active session title if it's the first message
    if (messages.length === 0) {
      setSessions((prev) =>
        prev.map((s) =>
          s.id === activeSessionId
            ? { ...s, title: query.slice(0, 36) + (query.length > 36 ? "..." : "") }
            : s
        )
      );
    }

    const assistantMsgId = `assistant-${Date.now()}`;

    // Stream live response from the backend
    const placeholderBotMessage: ChatMessage = {
      id: assistantMsgId,
      role: "assistant",
      content: "",
      isStreaming: true,
      timestamp: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, placeholderBotMessage]);

    try {
      const historyPayload = messages.map((m) => ({
        role: m.role,
        content: m.content,
      }));

      let accumulatedText = "";

      const controller = api.streamChat(query, historyPayload, {
        onStep: (step: ResearchStep) => {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsgId
                ? {
                    ...m,
                    isResearching: step.status !== "completed",
                    researchSteps: (() => {
                      const existing = m.researchSteps || [];
                      const idx = existing.findIndex((s) => s.id === step.id);
                      if (idx >= 0) {
                        const next = [...existing];
                        next[idx] = step;
                        return next;
                      }
                      return [...existing, step];
                    })(),
                  }
                : m
            )
          );
        },
        onBlock: (block: ResearchBlock) => {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsgId
                ? {
                    ...m,
                    blocks: [...(m.blocks || []), block],
                  }
                : m
            )
          );
        },
        onToken: (chunk: string) => {
          accumulatedText += chunk;
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsgId
                ? {
                    ...m,
                    content: accumulatedText,
                    isStreaming: true,
                  }
                : m
            )
          );
        },
        onCitation: (citations: Citation[]) => {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsgId
                ? {
                    ...m,
                    citations,
                  }
                : m
            )
          );
        },
        onDone: () => {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsgId
                ? {
                    ...m,
                    isStreaming: false,
                  }
                : m
            )
          );
          setLoading(false);
        },
        onError: (err: Error) => {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsgId
                ? {
                    ...m,
                    content: `Communication error: ${err.message || "Failed to reach inference server."}`,
                    isStreaming: false,
                  }
                : m
            )
          );
          setLoading(false);
        },
      }, options);

      abortControllerRef.current = controller;
    } catch (err: any) {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantMsgId
            ? {
                ...m,
                content: `Error contacting research engine: ${
                  err?.message || "Please check backend connection."
                }`,
                isStreaming: false,
              }
            : m
        )
      );
      setLoading(false);
    }
  };

  const handleStop = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setLoading(false);
    setMessages((prev) =>
      prev.map((m) => (m.isStreaming ? { ...m, isStreaming: false } : m))
    );
  };

  // Render assistant content with clickable [1], [2], [F{id}], [W{id}] footnotes, hover tooltips, and interactive tables
  const renderMessageMarkdown = (
    content: string,
    isStreaming?: boolean,
    citations?: Citation[]
  ) => {
    // Regex matches [1], [2], [12], [F1], [F:123], [W1], [W2]
    const CITATION_REGEX = /(\[(?:[0-9]+|F:?[a-zA-Z0-9_\-]+|W[0-9]+)\])/g;

    const paragraphs = content.split(/\n\n+/);

    return (
      <div className="text-[14px] sm:text-[15px] leading-relaxed space-y-3 text-foreground/95">
        {paragraphs.map((para, pIdx) => {
          const trimmed = para.trim();

          // Markdown table: render whole table with remarkGfm directly
          if (trimmed.startsWith("|") || trimmed.includes("\n|")) {
            return (
              <ReactMarkdown
                key={pIdx}
                remarkPlugins={[remarkGfm]}
                components={{
                  table: ({ children }) => (
                    <div className="my-3 w-full overflow-x-auto rounded-lg border border-border/80 bg-card/40 shadow-xs">
                      <table className="w-full text-xs caption-bottom text-left border-collapse">
                        {children}
                      </table>
                    </div>
                  ),
                  thead: ({ children }) => (
                    <thead className="border-b border-border/70 bg-muted/40 text-muted-foreground font-mono text-[11px] uppercase tracking-wider">
                      {children}
                    </thead>
                  ),
                  tbody: ({ children }) => (
                    <tbody className="divide-y divide-border/50 [&_tr:hover]:bg-muted/30 transition-colors">
                      {children}
                    </tbody>
                  ),
                  tr: ({ children }) => (
                    <tr className="transition-colors hover:bg-muted/20">
                      {children}
                    </tr>
                  ),
                  th: ({ children }) => (
                    <th className="px-3 py-2 text-left font-medium text-foreground whitespace-nowrap">
                      {children}
                    </th>
                  ),
                  td: ({ children }) => (
                    <td className="px-3 py-2 font-mono text-xs text-foreground/90 whitespace-nowrap">
                      {children}
                    </td>
                  ),
                }}
              >
                {para}
              </ReactMarkdown>
            );
          }

          // Regular paragraph or list: split by inline citations
          const parts = para.split(CITATION_REGEX);

          return (
            <div key={pIdx} className="leading-relaxed">
              {parts.map((part, idx) => {
                const isCitation = CITATION_REGEX.test(part);
                CITATION_REGEX.lastIndex = 0;

                if (isCitation) {
                  return (
                    <CitationBadge
                      key={idx}
                      token={part}
                      citations={citations}
                      onOpenEvidence={handleCitationClick}
                    />
                  );
                }

                if (!part) return null;

                return (
                  <ReactMarkdown
                    key={idx}
                    remarkPlugins={[remarkGfm]}
                    components={{
                      p: ({ children }) => <span className="inline">{children}</span>,
                      ul: ({ children }) => (
                        <ul className="list-disc pl-5 space-y-1.5 my-2 block">{children}</ul>
                      ),
                      ol: ({ children }) => (
                        <ol className="list-decimal pl-5 space-y-1.5 my-2 block">{children}</ol>
                      ),
                      li: ({ children }) => <li className="my-0.5">{children}</li>,
                      strong: ({ children }) => (
                        <strong className="font-semibold text-foreground">{children}</strong>
                      ),
                      code: ({ children }) => (
                        <code className="rounded bg-muted/60 px-1.5 py-0.5 font-mono text-xs text-foreground">
                          {children}
                        </code>
                      ),
                    }}
                  >
                    {part}
                  </ReactMarkdown>
                );
              })}
            </div>
          );
        })}
        {isStreaming && (
          <span className="inline-block w-1.5 h-4 ml-1 bg-emerald-400 animate-pulse rounded-[1px] align-middle" />
        )}
      </div>
    );
  };

  return (
    <div className="flex h-full w-full overflow-hidden bg-background text-foreground">
      {/* Main Conversational Center Canvas */}
      <div className="flex-1 flex flex-col h-full min-w-0 relative">
        {/* Minimal ChatGPT Header */}
        <header className="h-12 border-b border-border/70 px-3 sm:px-4 flex items-center justify-between bg-background/80 backdrop-blur-md z-20">
          <div className="flex items-center gap-2">
            {/* Session Indicator */}
            <div className="flex items-center gap-1.5 px-3 py-1 text-xs font-semibold text-foreground">
              <span>Session</span>
              <Badge variant="outline" className="text-[9px] font-mono px-1 py-0 h-3.5 border-emerald-500/30 text-emerald-400">
                Sources available
              </Badge>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {/* Secondary Insights Sidebar Toggle */}
            <Button
              variant="outline"
              size="sm"
              onClick={() => setRightSidebarOpen(!rightSidebarOpen)}
              className={cn(
                "h-8 px-2.5 text-xs border-border/80 transition-all cursor-pointer active:scale-95",
                rightSidebarOpen
                  ? "bg-accent text-foreground font-semibold shadow-xs"
                  : "text-muted-foreground hover:text-foreground"
              )}
              title="Toggle research insights sidebar"
            >
              <Compass className="size-3.5 mr-1.5 text-emerald-400" />
              <span>Findings</span>
              {currentArtifacts.length > 0 && (
                <span className="ml-1.5 size-4 rounded-full bg-emerald-500/20 text-emerald-400 text-[10px] font-mono font-bold flex items-center justify-center">
                  {Math.min(currentArtifacts.length, 2)}
                </span>
              )}
            </Button>
          </div>
        </header>

        {/* Messages & Content Canvas */}
        <div
          ref={messagesContainerRef}
          onScroll={handleScroll}
          className="flex-1 overflow-y-auto px-4 sm:px-6 md:px-8 py-6 space-y-6"
        >
          {messages.length === 0 ? (
            /* ChatGPT-style Editorial Empty State */
            <div className="h-full flex flex-col items-center justify-center max-w-3xl mx-auto text-center px-4 space-y-8 my-auto">
              <div className="space-y-2.5">
                <h1 className="text-xl sm:text-2xl font-semibold tracking-tight text-foreground max-w-2xl mx-auto leading-[1.1]">
                  What do you want to investigate?
                </h1>
                <p className="text-xs sm:text-sm text-muted-foreground max-w-lg mx-auto leading-relaxed">
                  Ask about your documents, financial metrics, or disclosures.
                </p>
              </div>

              {/* Floating Composer in Center (Screenshot 1 & 2) */}
              <div className="w-full">
                <ChatComposer
                  onSend={handleSend}
                  loading={loading}
                  onStop={handleStop}
                  onUploadFile={handleUploadFile}
                  placeholder="Ask about your documents..."
                />
              </div>


            </div>
          ) : (
            /* Conversational Stream */
            <TooltipProvider delay={100}>
              <div className="max-w-3xl mx-auto space-y-6 pb-28">
                {messages.map((msg) => (
                  <div
                    key={msg.id}
                    className={cn(
                      "flex flex-col space-y-2 animate-in fade-in-50 slide-in-from-bottom-2 duration-300",
                      msg.role === "user" ? "items-end" : "items-start"
                    )}
                  >
                    {msg.role === "user" ? (
                      /* User message bubble */
                      <div className="max-w-[85%] rounded-2xl bg-muted/70 border border-border/70 px-4 py-2.5 text-sm text-foreground shadow-xs">
                        {msg.content}
                      </div>
                    ) : (
                      /* Assistant Response */
                      <div className="w-full space-y-4">
                        {/* Subtle Research Progression Stepper */}
                        {msg.researchSteps && (
                          <ResearchProgress
                            steps={msg.researchSteps}
                            isSearching={msg.isResearching}
                          />
                        )}

                        {/* Typing indicator while receiving initial SSE tokens */}
                        {msg.isStreaming && !msg.content && !msg.researchSteps && (
                          <div className="flex items-center gap-2 py-2 px-1 text-muted-foreground font-mono text-xs">
                            <div className="flex items-center gap-1">
                              <span className="size-2 rounded-full bg-emerald-400 animate-bounce [animation-delay:-0.3s]" />
                              <span className="size-2 rounded-full bg-emerald-400 animate-bounce [animation-delay:-0.15s]" />
                              <span className="size-2 rounded-full bg-emerald-400 animate-bounce" />
                            </div>
                            <span className="text-zinc-400 text-[11px]">Streaming response...</span>
                          </div>
                        )}

                        {/* Main prose text */}
                        {msg.content && (
                          <div className="space-y-2 pl-1">
                            {renderMessageMarkdown(msg.content, msg.isStreaming, msg.citations)}
                          </div>
                        )}

                        {/* Dynamic Structured Blocks (Charts, Tables, Findings, Metrics) */}
                        {msg.blocks && msg.blocks.length > 0 && (
                          <div className="space-y-4 pt-1">
                            {msg.blocks.map((block) => (
                              <ResearchBlockRenderer
                                key={block.id}
                                block={block}
                                onOpenEvidence={handleCitationClick}
                              />
                            ))}
                          </div>
                        )}

                        {/* Action footer */}
                        <div className="flex items-center gap-2 pt-1 pl-1 text-xs text-muted-foreground">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleCopyMessage(msg.id, msg.content)}
                            className="h-7 px-2 text-[11px] text-muted-foreground hover:text-foreground"
                            title="Copy response"
                          >
                            {copiedMessageId === msg.id ? (
                              <Check className="size-3 text-emerald-400 mr-1" />
                            ) : (
                              <Copy className="size-3 mr-1" />
                            )}
                            <span>Copy</span>
                          </Button>

                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleSend(messages[messages.length - 2]?.content || "Retry")}
                            className="h-7 px-2 text-[11px] text-muted-foreground hover:text-foreground"
                            title="Retry"
                          >
                            <RotateCcw className="size-3 mr-1" />
                            <span>Retry</span>
                          </Button>
                        </div>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </TooltipProvider>
          )}
        </div>

        {/* Bottom Anchored Composer (When chat is active) */}
        {messages.length > 0 && (
          <div className="absolute bottom-0 left-0 right-0 p-4 bg-gradient-to-t from-background via-background/95 to-transparent z-10">
            <div className="max-w-3xl mx-auto space-y-1.5">
              <ChatComposer
                onSend={handleSend}
                loading={loading}
                onStop={handleStop}
                onUploadFile={handleUploadFile}
                placeholder="Ask a follow-up..."
              />
              <p className="text-center text-[10px] text-muted-foreground/60 font-mono">
                Click citations to inspect source documents.
              </p>
            </div>
          </div>
        )}
      </div>

      {/* 3. Secondary Research & Insights Sidebar (Surfacing top 2 artifacts) */}
      <ResearchSidebar
        artifacts={currentArtifacts}
        blocks={currentBlocks}
        onNavigateToBlock={handleNavigateToBlock}
        open={rightSidebarOpen}
        onToggle={() => setRightSidebarOpen(!rightSidebarOpen)}
      />

      {/* 4. Slide-Over Evidence Sheet with PDF BBox Viewer */}
      <EvidenceSheet
        factId={selectedFactId}
        open={sheetOpen}
        onOpenChange={setSheetOpen}
        onSelectCounterpart={(counterpartId) => setSelectedFactId(counterpartId)}
      />
    </div>
  );
}
