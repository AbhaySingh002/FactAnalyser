"use client";

import React, { createContext, useContext, useState, ReactNode } from "react";

export interface SessionSummary {
  id: string;
  title: string;
  timestamp: string;
}

const INITIAL_SESSIONS: SessionSummary[] = [
  {
    id: "sess-current",
    title: "Cross-Filing Due-Diligence Audit",
    timestamp: "Just now",
  },
  {
    id: "sess-1",
    title: "SaaS Net Retention Benchmark",
    timestamp: "2h ago",
  },
  {
    id: "sess-2",
    title: "Cap Table & Dilution Disclosures",
    timestamp: "Yesterday",
  },
  {
    id: "sess-3",
    title: "Debt Covenant Compliance Review",
    timestamp: "3 days ago",
  },
];

interface ChatSessionContextType {
  sessions: SessionSummary[];
  activeSessionId: string;
  setActiveSessionId: (id: string) => void;
  setSessions: React.Dispatch<React.SetStateAction<SessionSummary[]>>;
  handleNewChat: () => void;
  handleDeleteSession: (id: string) => void;
}

const ChatSessionContext = createContext<ChatSessionContextType | undefined>(undefined);

export function ChatSessionProvider({ children }: { children: ReactNode }) {
  const [sessions, setSessions] = useState<SessionSummary[]>(INITIAL_SESSIONS);
  const [activeSessionId, setActiveSessionId] = useState("sess-current");

  const handleNewChat = () => {
    const newId = `sess-${Date.now()}`;
    const newSession: SessionSummary = {
      id: newId,
      title: "New Session",
      timestamp: "Just now",
    };
    setSessions((prev) => [newSession, ...prev]);
    setActiveSessionId(newId);
  };

  const handleDeleteSession = (id: string) => {
    setSessions((prev) => prev.filter((s) => s.id !== id));
    if (activeSessionId === id) {
      handleNewChat();
    }
  };

  return (
    <ChatSessionContext.Provider
      value={{
        sessions,
        activeSessionId,
        setActiveSessionId,
        setSessions,
        handleNewChat,
        handleDeleteSession,
      }}
    >
      {children}
    </ChatSessionContext.Provider>
  );
}

export function useChatSession() {
  const context = useContext(ChatSessionContext);
  if (context === undefined) {
    throw new Error("useChatSession must be used within a ChatSessionProvider");
  }
  return context;
}
