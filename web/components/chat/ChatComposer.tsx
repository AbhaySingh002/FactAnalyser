"use client";

import React, { useState, useRef, useEffect } from "react";
import {
  Plus,
  ArrowUp,
  Square,
  Globe,
  BrainCircuit,
  FileUp,
  FolderOpen,
  Mic,
  Sparkles,
  Search,
  SlidersHorizontal,
  Check,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

interface ChatComposerProps {
  onSend: (message: string, options: { deepResearch: boolean; webSearch: boolean }) => void;
  loading: boolean;
  onStop?: () => void;
  onUploadFile?: (file: File) => void;
  placeholder?: string;
  className?: string;
}

export function ChatComposer({
  onSend,
  loading,
  onStop,
  onUploadFile,
  placeholder = "Ask about your documents...",
  className,
}: ChatComposerProps) {
  const [input, setInput] = useState("");
  const [deepResearch, setDeepResearch] = useState(true);
  const [webSearch, setWebSearch] = useState(true);
  const [menuOpen, setMenuOpen] = useState(false);

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Auto-resize textarea height
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = `${Math.min(
        textareaRef.current.scrollHeight,
        200
      )}px`;
    }
  }, [input]);

  const handleSubmit = () => {
    const trimmed = input.trim();
    if (!trimmed || loading) return;
    onSend(trimmed, { deepResearch, webSearch });
    setInput("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file && onUploadFile) {
      onUploadFile(file);
    }
    if (e.target) {
      e.target.value = "";
    }
  };

  return (
    <div
      className={cn(
        "relative p-1.5 rounded-[2.25rem] bg-white/[0.04] dark:bg-white/[0.02] border border-border/80 shadow-2xl ring-1 ring-border/20 transition-all duration-300 focus-within:border-emerald-500/50 focus-within:ring-2 focus-within:ring-emerald-500/15",
        className
      )}
    >
      <input
        type="file"
        ref={fileInputRef}
        onChange={handleFileChange}
        accept=".pdf,.csv,.xlsx,.txt"
        className="hidden"
      />

      {/* Inner Core Container */}
      <div className="p-2.5 rounded-[calc(2.25rem-0.375rem)] bg-card/85 backdrop-blur-2xl shadow-[inset_0_1px_1px_rgba(255,255,255,0.08)] flex flex-col justify-between">

      {/* Main text area */}
      <div className="flex items-start px-3 pt-1.5 pb-2">
        <Textarea
          ref={textareaRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          rows={1}
          className="min-h-[36px] max-h-48 w-full resize-none border-0 bg-transparent p-0 text-sm sm:text-[15px] font-normal text-foreground placeholder:text-muted-foreground/75 focus-visible:ring-0 focus-visible:outline-none shadow-none leading-relaxed tracking-normal"
        />
      </div>

      {/* Control Bar below input */}
      <div className="flex items-center justify-between gap-3 px-2 pt-1 pb-0.5">
        {/* Left tools menu */}
        <div className="flex items-center gap-1.5">
          {/* ChatGPT-style + button */}
          <DropdownMenu open={menuOpen} onOpenChange={setMenuOpen}>
            <DropdownMenuTrigger
              className="size-8 rounded-full p-0 flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-muted/70 transition-colors focus:outline-none"
              title="Add files or toggles"
            >
              <Plus className="size-4" />
            </DropdownMenuTrigger>

            <DropdownMenuContent
              align="start"
              sideOffset={8}
              className="w-72 p-1.5 rounded-2xl border-border/80 bg-popover/95 backdrop-blur-xl shadow-2xl space-y-1"
            >
              <DropdownMenuItem
                onClick={() => fileInputRef.current?.click()}
                className="rounded-xl px-3 py-2 cursor-pointer flex items-center gap-3 text-xs"
              >
                <div className="size-7 rounded-lg bg-emerald-500/10 text-emerald-400 flex items-center justify-center shrink-0">
                  <FileUp className="size-4" />
                </div>
                <div className="flex flex-col">
                  <span className="font-semibold text-foreground">Add photos & files</span>
                  <span className="text-[10px] text-muted-foreground">Upload 10-K, pitch decks, filings</span>
                </div>
              </DropdownMenuItem>

              <DropdownMenuItem
                onClick={() => setDeepResearch(!deepResearch)}
                className="rounded-xl px-3 py-2 cursor-pointer flex items-center justify-between text-xs"
              >
                <div className="flex items-center gap-3">
                  <div className="size-7 rounded-lg bg-sky-500/10 text-sky-400 flex items-center justify-center shrink-0">
                    <BrainCircuit className="size-4" />
                  </div>
                  <div className="flex flex-col">
                    <span className="font-semibold text-foreground">Deep research</span>
                    <span className="text-[10px] text-muted-foreground">Deep research across all documents</span>
                  </div>
                </div>
                {deepResearch && <Check className="size-3.5 text-emerald-400" />}
              </DropdownMenuItem>

              <DropdownMenuItem
                onClick={() => setWebSearch(!webSearch)}
                className="rounded-xl px-3 py-2 cursor-pointer flex items-center justify-between text-xs"
              >
                <div className="flex items-center gap-3">
                  <div className="size-7 rounded-lg bg-emerald-500/10 text-emerald-400 flex items-center justify-center shrink-0">
                    <Globe className="size-4" />
                  </div>
                  <div className="flex flex-col">
                    <span className="font-semibold text-foreground">Web search</span>
                    <span className="text-[10px] text-muted-foreground">Search external market benchmarks</span>
                  </div>
                </div>
                {webSearch && <Check className="size-3.5 text-emerald-400" />}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>

          {/* Deep Research Toggle Pill */}
          <button
            type="button"
            onClick={() => setDeepResearch(!deepResearch)}
            className={cn(
              "inline-flex items-center gap-1.5 h-7 px-2.5 rounded-full text-xs font-mono transition-all border",
              deepResearch
                ? "bg-emerald-500/15 border-emerald-500/40 text-emerald-400 font-semibold"
                : "bg-muted/30 border-border/70 text-muted-foreground hover:text-foreground"
            )}
            title="Toggle deep research"
          >
            <BrainCircuit className="size-3" />
            <span>Deep research</span>
            {deepResearch && (
              <span className="size-1.5 rounded-full bg-emerald-400 animate-pulse" />
            )}
          </button>

          {/* Web search toggle pill */}
          {webSearch && (
            <button
              type="button"
              onClick={() => setWebSearch(!webSearch)}
              className="hidden sm:inline-flex items-center gap-1 h-7 px-2 rounded-full text-[11px] font-mono bg-muted/40 border border-border/60 text-muted-foreground hover:text-foreground transition-colors"
              title="Web search active"
            >
              <Globe className="size-3 text-sky-400" />
              <span>Search</span>
            </button>
          )}
        </div>

        {/* Right side submit & voice action */}
        <div className="flex items-center gap-1.5">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="size-8 rounded-full p-0 text-muted-foreground hover:text-foreground hover:bg-muted/70 transition-colors hidden sm:flex items-center justify-center"
            title="Voice input"
          >
            <Mic className="size-4" />
          </Button>

          {loading ? (
            <Button
              type="button"
              onClick={onStop}
              size="sm"
              className="size-8 rounded-full p-0 bg-foreground text-background hover:bg-foreground/90 transition-transform active:scale-95"
              title="Stop generating"
            >
              <Square className="size-3 fill-current" />
            </Button>
          ) : (
            <Button
              type="button"
              onClick={handleSubmit}
              disabled={!input.trim()}
              size="sm"
              className={cn(
                "size-8 rounded-full p-0 transition-all active:scale-95 duration-200",
                input.trim()
                  ? "bg-emerald-500 text-zinc-950 hover:bg-emerald-400"
                  : "bg-muted/70 text-muted-foreground/50 cursor-not-allowed"
              )}
              title="Send message (Enter)"
            >
              <ArrowUp className="size-4 stroke-[2.5]" />
            </Button>
          )}
        </div>
      </div>
    </div>
  </div>
  );
}
