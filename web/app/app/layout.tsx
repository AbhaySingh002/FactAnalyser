"use client";

import React from "react";
import { WorkspaceShell } from "@/components/layout/WorkspaceShell";
import { ChatSessionProvider } from "@/components/chat/ChatSessionContext";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <ChatSessionProvider>
      <WorkspaceShell>{children}</WorkspaceShell>
    </ChatSessionProvider>
  );
}
