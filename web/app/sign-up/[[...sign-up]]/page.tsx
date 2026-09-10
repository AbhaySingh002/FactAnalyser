"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { SignUp as ClerkSignUp } from "@clerk/nextjs";
import { isClerkConfigured, useAuth } from "@/components/auth/AuthProvider";
import { ArrowRight, Shield, Lock, Check } from "lucide-react";

export default function SignUpPage() {
  const router = useRouter();
  const { signIn } = useAuth();
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const handleDemoSignUp = (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setTimeout(() => {
      signIn(email || "analyst@fincracker.internal");
      router.push("/app");
    }, 400);
  };

  const handleGoogleSignUp = () => {
    setIsLoading(true);
    setTimeout(() => {
      signIn("google.user@institution.com");
      router.push("/app");
    }, 400);
  };

  return (
    <div className="min-h-[100dvh] flex flex-col justify-between bg-background text-foreground">
      {/* Top Bar */}
      <header className="px-6 py-5 max-w-7xl mx-auto w-full flex items-center justify-between">
        <Link href="/" className="flex items-center gap-2.5">
          <div className="flex size-7 items-center justify-center rounded-md bg-primary text-primary-foreground text-xs font-semibold tracking-tight">
            FC
          </div>
          <span className="text-sm font-semibold tracking-tight text-foreground">
            FIN Cracker
          </span>
        </Link>
        <Link
          href="/"
          className="text-xs text-muted-foreground hover:text-foreground transition-colors font-medium"
        >
          Return to home
        </Link>
      </header>

      {/* Main Container */}
      <main className="flex-1 flex items-center justify-center px-4 py-12">
        <div className="w-full max-w-[420px]">
          {/* Card Frame with Double Bezel */}
          <div className="rounded-2xl border border-border bg-card p-7 sm:p-8 shadow-xs">
            {/* Header */}
            <div className="mb-6 space-y-1.5 text-left">
              <h1 className="text-xl font-semibold tracking-tight text-foreground">
                Create an account
              </h1>
              <p className="text-xs text-muted-foreground">
                Start financial document analysis.
              </p>
            </div>

            {isClerkConfigured ? (
              <ClerkSignUp
                routing="path"
                path="/sign-up"
                signInUrl="/sign-in"
                fallbackRedirectUrl="/app"
                appearance={{
                  elements: {
                    rootBox: "w-full",
                    card: "shadow-none p-0 border-0 bg-transparent",
                    header: "hidden",
                    formButtonPrimary:
                      "bg-primary hover:bg-primary/90 text-primary-foreground text-xs font-semibold h-10 rounded-lg",
                    formFieldInput:
                      "rounded-lg border-border text-xs h-10 focus:ring-1 focus:ring-primary",
                    footerAction: "text-xs text-muted-foreground",
                  },
                }}
              />
            ) : (
              <div className="space-y-4">
                {/* Google Sign-up */}
                <button
                  type="button"
                  onClick={handleGoogleSignUp}
                  disabled={isLoading}
                  className="w-full h-10 px-4 rounded-lg border border-border bg-muted/30 hover:bg-muted/60 text-foreground text-xs font-medium flex items-center justify-center gap-2.5 transition-colors cursor-pointer active:scale-[0.99]"
                >
                  <svg className="size-4" viewBox="0 0 24 24">
                    <path
                      fill="#4285F4"
                      d="M23.745 12.27c0-.7-.06-1.4-.19-2.07H12v4.51h6.6c-.29 1.52-1.14 2.82-2.4 3.68v3.05h3.88c2.27-2.09 3.665-5.17 3.665-9.17Z"
                    />
                    <path
                      fill="#34A853"
                      d="M12 24c3.24 0 5.95-1.08 7.93-2.91l-3.88-3.05c-1.08.72-2.45 1.16-4.05 1.16-3.12 0-5.77-2.1-6.72-4.93H1.25v3.15C3.26 21.36 7.34 24 12 24Z"
                    />
                    <path
                      fill="#FBBC05"
                      d="M5.28 14.27A7.195 7.195 0 0 1 4.9 12c0-.79.14-1.56.38-2.27V6.58H1.25A11.96 11.96 0 0 0 0 12c0 1.92.45 3.74 1.25 5.42l4.03-3.15Z"
                    />
                    <path
                      fill="#EA4335"
                      d="M12 4.75c1.77 0 3.35.61 4.6 1.8l3.42-3.42C17.95 1.19 15.24 0 12 0 7.34 0 3.26 2.64 1.25 6.58l4.03 3.15c.95-2.83 3.6-4.98 6.72-4.98Z"
                    />
                  </svg>
                  <span>Sign up with Google</span>
                </button>

                <div className="relative flex items-center justify-center text-[10px] uppercase text-muted-foreground tracking-wider py-1">
                  <span className="bg-card px-2 relative z-10">or work credentials</span>
                  <div className="absolute inset-0 flex items-center">
                    <div className="w-full border-t border-border" />
                  </div>
                </div>

                {/* Form */}
                <form onSubmit={handleDemoSignUp} className="space-y-3">
                  <div className="space-y-1">
                    <label className="text-xs font-medium text-foreground block">
                      Full name
                    </label>
                    <input
                      type="text"
                      value={fullName}
                      onChange={(e) => setFullName(e.target.value)}
                      placeholder="Elena Vance"
                      className="w-full h-10 px-3 rounded-lg border border-border bg-transparent text-xs text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:ring-1 focus:ring-primary transition-all"
                    />
                  </div>

                  <div className="space-y-1">
                    <label className="text-xs font-medium text-foreground block">
                      Work email
                    </label>
                    <input
                      type="email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder="analyst@firm.com"
                      className="w-full h-10 px-3 rounded-lg border border-border bg-transparent text-xs text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:ring-1 focus:ring-primary transition-all"
                    />
                  </div>

                  <button
                    type="submit"
                    disabled={isLoading}
                    className="w-full h-10 px-4 rounded-lg bg-primary hover:bg-primary/90 text-primary-foreground text-xs font-semibold flex items-center justify-center gap-2 transition-all cursor-pointer active:scale-[0.99]"
                  >
                    <span>{isLoading ? "Creating account..." : "Start an analysis"}</span>
                    <ArrowRight className="size-3.5" />
                  </button>
                </form>

                <div className="pt-2 text-center text-xs text-muted-foreground">
                  Already have an account?{" "}
                  <Link
                    href="/sign-in"
                    className="text-foreground underline underline-offset-4 font-medium hover:text-foreground/80"
                  >
                    Sign in
                  </Link>
                </div>
              </div>
            )}
          </div>

          {/* Security footnote */}
          <div className="mt-6 flex items-center justify-center gap-4 text-[11px] text-muted-foreground">
            <div className="flex items-center gap-1.5">
              <Shield className="size-3 text-emerald-500" />
              <span>SOC 2 Compliant</span>
            </div>
            <span>&middot;</span>
            <div className="flex items-center gap-1.5">
              <Lock className="size-3 text-zinc-400" />
              <span>Isolated Data Enclave</span>
            </div>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="px-6 py-4 text-center text-[11px] text-muted-foreground">
        FIN Cracker &middot; Financial Document Analysis
      </footer>
    </div>
  );
}
