"use client";

import React, { createContext, useContext, useState, useEffect } from "react";
import Link from "next/link";
import { ClerkProvider, SignedIn as ClerkSignedIn, SignedOut as ClerkSignedOut, UserButton as ClerkUserButton, useUser as useClerkUser } from "@clerk/nextjs";

// Check if Clerk publishable key is present and configured
export const isClerkConfigured = Boolean(
  process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY &&
  process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY.startsWith("pk_")
);

interface FallbackAuthContextType {
  isSignedIn: boolean;
  signIn: (email?: string) => void;
  signOut: () => void;
  user: {
    fullName: string;
    email: string;
    avatarUrl?: string;
  } | null;
}

const FallbackAuthContext = createContext<FallbackAuthContextType>({
  isSignedIn: false,
  signIn: () => {},
  signOut: () => {},
  user: null,
});

const DEMO_USER = {
  fullName: "Senior Financial Analyst",
  email: "analyst@fincracker.internal",
  avatarUrl: "",
};

export function FallbackAuthProvider({ children }: { children: React.ReactNode }) {
  const [isSignedIn, setIsSignedIn] = useState(false);

  useEffect(() => {
    try {
      const stored = localStorage.getItem("fin_cracker_auth_demo");
      if (stored === "true") {
        setIsSignedIn(true);
      }
    } catch {
      // ignore
    }
  }, []);

  const signIn = () => {
    setIsSignedIn(true);
    try {
      localStorage.setItem("fin_cracker_auth_demo", "true");
    } catch {
      // ignore
    }
  };

  const signOut = () => {
    setIsSignedIn(false);
    try {
      localStorage.removeItem("fin_cracker_auth_demo");
    } catch {
      // ignore
    }
  };

  return (
    <FallbackAuthContext.Provider
      value={{
        isSignedIn,
        signIn,
        signOut,
        user: isSignedIn ? DEMO_USER : null,
      }}
    >
      {children}
    </FallbackAuthContext.Provider>
  );
}

export function useAuth() {
  const fallback = useContext(FallbackAuthContext);
  if (isClerkConfigured) {
    // If Clerk is configured, use Clerk hooks inside ClerkProvider
    return {
      isClerk: true,
      isSignedIn: false, // Handled by Clerk components
      signIn: () => {},
      signOut: () => {},
      user: null,
    };
  }
  return {
    isClerk: false,
    isSignedIn: fallback.isSignedIn,
    signIn: fallback.signIn,
    signOut: fallback.signOut,
    user: fallback.user,
  };
}

export function SignedIn({ children }: { children: React.ReactNode }) {
  const fallback = useContext(FallbackAuthContext);
  if (isClerkConfigured) {
    return <ClerkSignedIn>{children}</ClerkSignedIn>;
  }
  return fallback.isSignedIn ? <>{children}</> : null;
}

export function SignedOut({ children }: { children: React.ReactNode }) {
  const fallback = useContext(FallbackAuthContext);
  if (isClerkConfigured) {
    return <ClerkSignedOut>{children}</ClerkSignedOut>;
  }
  return !fallback.isSignedIn ? <>{children}</> : null;
}

export function UserButton() {
  const fallback = useContext(FallbackAuthContext);
  if (isClerkConfigured) {
    return (
      <ClerkUserButton
        appearance={{
          elements: {
            userButtonAvatarBox: "size-8 rounded-full border border-border",
          },
        }}
      />
    );
  }

  return (
    <div className="flex items-center justify-between gap-2 w-full">
      <div className="flex items-center gap-2 min-w-0">
        <div className="flex size-7 items-center justify-center rounded bg-secondary text-secondary-foreground text-[10px] font-mono font-bold border border-border shrink-0">
          FA
        </div>
        <div className="flex flex-col min-w-0">
          <span className="text-xs font-medium text-foreground truncate leading-none">
            {fallback.user?.fullName || "Senior Analyst"}
          </span>
          <span className="text-[10px] font-mono text-muted-foreground truncate leading-tight mt-0.5">
            {fallback.user?.email || "internal"}
          </span>
        </div>
      </div>
      <button
        onClick={fallback.signOut}
        className="text-[10px] font-mono text-muted-foreground hover:text-foreground transition-colors px-1.5 py-1 rounded hover:bg-muted/70 shrink-0"
        title="Sign out"
      >
        Sign out
      </button>
    </div>
  );
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  if (isClerkConfigured) {
    return <ClerkProvider>{children}</ClerkProvider>;
  }
  return <FallbackAuthProvider>{children}</FallbackAuthProvider>;
}
