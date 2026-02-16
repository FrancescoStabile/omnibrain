/**
 * Onboarding — 4-step "Holy Shit" experience.
 *
 * Step 1  Welcome   — hero + [Start Free] button
 * Step 2  Connect   — Google OAuth button
 * Step 3  Analyzing — animated progress
 * Step 4  Reveal    — greeting + stats + insight cards
 *
 * Goal: < 30 seconds from click to first insight.
 */

"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import type { InsightCard as InsightCardType, OnboardingResult } from "@/lib/api";
import { useStore } from "@/lib/store";
import { cn } from "@/lib/utils";

// ═══════════════════════════════════════════════════════════════════════════
// Sub-components
// ═══════════════════════════════════════════════════════════════════════════

function StepIndicator({ current }: { current: number }) {
  return (
    <div className="flex gap-2 justify-center mb-8">
      {[0, 1, 2, 3].map((i) => (
        <div
          key={i}
          className={cn(
            "h-1.5 rounded-full transition-all duration-500",
            i === current
              ? "w-8 bg-[var(--brand-primary)]"
              : i < current
                ? "w-4 bg-[var(--brand-primary)] opacity-40"
                : "w-4 bg-[var(--border-default)]",
          )}
        />
      ))}
    </div>
  );
}

/** Animated counter that counts from 0 to `target` */
function AnimatedCount({ target, duration = 2000 }: { target: number; duration?: number }) {
  const [count, setCount] = useState(0);
  const ref = useRef<number | null>(null);

  useEffect(() => {
    if (target <= 0) {
      setCount(0);
      return;
    }
    const start = performance.now();
    const animate = (now: number) => {
      const elapsed = now - start;
      const progress = Math.min(elapsed / duration, 1);
      // Ease-out cubic
      const eased = 1 - Math.pow(1 - progress, 3);
      setCount(Math.round(eased * target));
      if (progress < 1) {
        ref.current = requestAnimationFrame(animate);
      }
    };
    ref.current = requestAnimationFrame(animate);
    return () => {
      if (ref.current) cancelAnimationFrame(ref.current);
    };
  }, [target, duration]);

  return <span>{count}</span>;
}

// ═══════════════════════════════════════════════════════════════════════════
// Step 1: Welcome
// ═══════════════════════════════════════════════════════════════════════════

function WelcomeStep({ onNext }: { onNext: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center min-h-[80vh] text-center px-6 animate-in fade-in slide-in-from-bottom-4 duration-700">
      {/* Brand logo / icon */}
      <div className="w-20 h-20 rounded-2xl bg-gradient-to-br from-[var(--brand-primary)] to-[var(--accent-orange)] flex items-center justify-center mb-8 shadow-lg shadow-[var(--brand-primary)]/20">
        <svg
          width="40"
          height="40"
          viewBox="0 0 24 24"
          fill="none"
          stroke="white"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M12 2a7 7 0 0 1 7 7c0 2.38-1.19 4.47-3 5.74V17a2 2 0 0 1-2 2H10a2 2 0 0 1-2-2v-2.26C6.19 13.47 5 11.38 5 9a7 7 0 0 1 7-7z" />
          <path d="M10 21h4" />
        </svg>
      </div>

      <h1 className="text-4xl font-bold mb-4 bg-gradient-to-r from-[var(--brand-primary)] to-[var(--accent-orange)] bg-clip-text text-transparent">
        OmniBrain
      </h1>

      <p className="text-xl text-[var(--text-secondary)] mb-2 max-w-md">
        Your AI that remembers everything.
      </p>

      <p className="text-sm text-[var(--text-tertiary)] mb-12 max-w-sm">
        Connect your Google account and get your first personalised briefing
        in under 30 seconds.
      </p>

      <button
        onClick={onNext}
        className="px-8 py-3 rounded-xl font-semibold text-white bg-gradient-to-r from-[var(--brand-primary)] to-[var(--accent-orange)] hover:opacity-90 transition-opacity shadow-lg shadow-[var(--brand-primary)]/25 text-lg"
      >
        Start Free
      </button>

      <p className="text-xs text-[var(--text-tertiary)] mt-6 max-w-xs">
        No sign-up. No email. Your data never leaves your machine.
      </p>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// Step 2: Connect Google
// ═══════════════════════════════════════════════════════════════════════════

function ConnectStep({ onConnected, onSkip }: { onConnected: () => void; onSkip: () => void }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleConnect = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const { auth_url } = await api.getOAuthUrl("gmail+calendar");
      // Redirect to Google consent screen
      window.location.href = auth_url;
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Failed to start OAuth";
      setError(msg);
      setLoading(false);
    }
  }, []);

  // Check if we just came back from OAuth callback
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("oauth") === "success") {
      // Clean URL
      window.history.replaceState({}, "", "/");
      onConnected();
    }
    if (params.get("oauth") === "error") {
      setError(params.get("message") || "OAuth failed");
      window.history.replaceState({}, "", "/");
    }
  }, [onConnected]);

  return (
    <div className="flex flex-col items-center justify-center min-h-[80vh] text-center px-6 animate-in fade-in slide-in-from-bottom-4 duration-700">
      {/* Google icon */}
      <div className="w-16 h-16 rounded-full bg-[var(--bg-secondary)] border border-[var(--border-default)] flex items-center justify-center mb-8">
        <svg width="28" height="28" viewBox="0 0 24 24">
          <path
            d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z"
            fill="#4285F4"
          />
          <path
            d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
            fill="#34A853"
          />
          <path
            d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
            fill="#FBBC05"
          />
          <path
            d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
            fill="#EA4335"
          />
        </svg>
      </div>

      <h2 className="text-2xl font-bold mb-3">Connect your Google account</h2>

      <p className="text-[var(--text-secondary)] mb-8 max-w-sm">
        We only read emails and calendar. Never send anything without your
        explicit permission.
      </p>

      <button
        onClick={handleConnect}
        disabled={loading}
        className={cn(
          "flex items-center gap-3 px-6 py-3 rounded-xl font-semibold",
          "bg-white text-gray-800 hover:bg-gray-50 transition-colors",
          "shadow-md border border-gray-200",
          loading && "opacity-60 cursor-not-allowed",
        )}
      >
        <svg width="20" height="20" viewBox="0 0 24 24">
          <path
            d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z"
            fill="#4285F4"
          />
          <path
            d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
            fill="#34A853"
          />
          <path
            d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
            fill="#FBBC05"
          />
          <path
            d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
            fill="#EA4335"
          />
        </svg>
        {loading ? "Connecting..." : "Continue with Google"}
      </button>

      {error && (
        <p className="text-sm text-red-400 mt-4 max-w-sm">{error}</p>
      )}

      <div className="flex items-center gap-4 mt-10 text-xs text-[var(--text-tertiary)]">
        <span className="flex items-center gap-1">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="11" width="18" height="11" rx="2" /><path d="M7 11V7a5 5 0 0 1 10 0v4" /></svg>
          Read-only access
        </span>
        <span className="flex items-center gap-1">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" /></svg>
          Local-first
        </span>
        <span className="flex items-center gap-1">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M23 21v-2a4 4 0 0 0-3-3.87" /><path d="M16 3.13a4 4 0 0 1 0 7.75" /></svg>
          Zero tracking
        </span>
      </div>

      <button
        onClick={onSkip}
        className="mt-8 text-sm text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] transition-colors underline underline-offset-2"
      >
        Skip for now — I&apos;ll connect later
      </button>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// Step 3: Analyzing
// ═══════════════════════════════════════════════════════════════════════════

const ANALYSIS_PHASES = [
  { label: "Reading your emails", icon: "📧", duration: 3000 },
  { label: "Learning your contacts", icon: "👥", duration: 2500 },
  { label: "Understanding your schedule", icon: "📅", duration: 2500 },
  { label: "Generating insights", icon: "✨", duration: 2000 },
] as const;

function AnalyzingStep({
  onComplete,
}: {
  onComplete: (result: OnboardingResult) => void;
}) {
  const [phaseIndex, setPhaseIndex] = useState(0);
  const [progress, setProgress] = useState(0);
  const apiCalled = useRef(false);
  const resultRef = useRef<OnboardingResult | null>(null);

  // Call the backend analysis once
  useEffect(() => {
    if (apiCalled.current) return;
    apiCalled.current = true;

    api
      .analyzeOnboarding()
      .then((r) => {
        resultRef.current = r;
      })
      .catch((e) => {
        console.error("Onboarding analysis failed:", e);
        // Still complete with empty result so the user isn't stuck
        resultRef.current = {
          greeting: "Welcome!",
          stats: { emails: 0, contacts: 0, events: 0 },
          insights: [],
          user_email: "",
          user_name: "",
          completed_at: new Date().toISOString(),
          duration_ms: 0,
        };
      });
  }, []);

  // Animate through analysis phases
  useEffect(() => {
    const totalDuration = ANALYSIS_PHASES.reduce((s, p) => s + p.duration, 0);
    let elapsed = 0;
    let currentPhase = 0;

    const interval = setInterval(() => {
      elapsed += 100;
      const pct = Math.min((elapsed / totalDuration) * 100, 100);
      setProgress(pct);

      // Advance phase
      let phaseTime = 0;
      for (let i = 0; i < ANALYSIS_PHASES.length; i++) {
        phaseTime += ANALYSIS_PHASES[i].duration;
        if (elapsed < phaseTime) {
          currentPhase = i;
          break;
        }
        if (i === ANALYSIS_PHASES.length - 1) {
          currentPhase = i;
        }
      }
      setPhaseIndex(currentPhase);

      if (elapsed >= totalDuration) {
        clearInterval(interval);
        // Wait for API result (may already be done)
        const waitForResult = () => {
          if (resultRef.current) {
            onComplete(resultRef.current);
          } else {
            setTimeout(waitForResult, 200);
          }
        };
        waitForResult();
      }
    }, 100);

    return () => clearInterval(interval);
  }, [onComplete]);

  const phase = ANALYSIS_PHASES[phaseIndex];

  return (
    <div className="flex flex-col items-center justify-center min-h-[80vh] text-center px-6">
      {/* Animated glow background */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[500px] h-[500px] rounded-full bg-[var(--brand-primary)] opacity-[0.04] blur-[100px] animate-pulse" />
      </div>

      <div className="relative z-10 flex flex-col items-center">
        {/* Phase icon */}
        <div className="text-5xl mb-8 animate-bounce">{phase.icon}</div>

        <p className="text-lg text-[var(--text-secondary)] mb-8 min-h-[2em] transition-all duration-500">
          {phase.label}...
        </p>

        {/* Progress bar */}
        <div className="w-64 h-1.5 bg-[var(--border-default)] rounded-full overflow-hidden mb-4">
          <div
            className="h-full bg-gradient-to-r from-[var(--brand-primary)] to-[var(--accent-orange)] rounded-full transition-all duration-200"
            style={{ width: `${progress}%` }}
          />
        </div>

        <p className="text-xs text-[var(--text-tertiary)]">
          This takes about 10 seconds
        </p>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// Step 4: Reveal
// ═══════════════════════════════════════════════════════════════════════════

function InsightCardComponent({
  card,
  index,
}: { card: InsightCardType; index: number }) {
  const iconMap: Record<string, string> = {
    mail: "📧",
    calendar: "📅",
    inbox: "📥",
    users: "👥",
    sparkles: "✨",
  };

  return (
    <div
      className="p-4 rounded-xl bg-[var(--bg-secondary)] border border-[var(--border-default)] animate-in fade-in slide-in-from-bottom-4"
      style={{ animationDelay: `${600 + index * 200}ms`, animationFillMode: "both" }}
    >
      <div className="flex items-start gap-3">
        <span className="text-xl">{iconMap[card.icon] || "💡"}</span>
        <div className="flex-1 min-w-0">
          <h4 className="font-semibold text-sm mb-1">{card.title}</h4>
          <p className="text-xs text-[var(--text-secondary)]">{card.body}</p>
          {card.action && (
            <button className="mt-2 text-xs text-[var(--brand-primary)] hover:underline">
              {card.action} →
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function RevealStep({
  result,
  onFinish,
}: { result: OnboardingResult; onFinish: () => void }) {
  const { stats } = result;

  return (
    <div className="flex flex-col items-center justify-center min-h-[80vh] px-6 py-12 max-w-lg mx-auto">
      {/* Greeting */}
      <h2
        className="text-3xl font-bold mb-8 animate-in fade-in duration-1000"
        style={{ animationFillMode: "both" }}
      >
        {result.greeting}
      </h2>

      {/* Stats row */}
      <div
        className="flex gap-6 mb-10 text-center animate-in fade-in duration-700"
        style={{ animationDelay: "300ms", animationFillMode: "both" }}
      >
        <div>
          <div className="text-2xl font-bold text-[var(--brand-primary)]">
            <AnimatedCount target={stats.emails || 0} />
          </div>
          <div className="text-xs text-[var(--text-tertiary)]">emails</div>
        </div>
        <div className="w-px bg-[var(--border-default)]" />
        <div>
          <div className="text-2xl font-bold text-[var(--brand-primary)]">
            <AnimatedCount target={stats.contacts || 0} />
          </div>
          <div className="text-xs text-[var(--text-tertiary)]">contacts</div>
        </div>
        <div className="w-px bg-[var(--border-default)]" />
        <div>
          <div className="text-2xl font-bold text-[var(--brand-primary)]">
            <AnimatedCount target={stats.events || 0} />
          </div>
          <div className="text-xs text-[var(--text-tertiary)]">events</div>
        </div>
      </div>

      {/* Insight cards */}
      {result.insights.length > 0 && (
        <div className="w-full space-y-3 mb-10">
          {result.insights.map((card, i) => (
            <InsightCardComponent key={i} card={card} index={i} />
          ))}
        </div>
      )}

      {/* Continue */}
      <button
        onClick={onFinish}
        className="px-8 py-3 rounded-xl font-semibold text-white bg-gradient-to-r from-[var(--brand-primary)] to-[var(--accent-orange)] hover:opacity-90 transition-opacity shadow-lg shadow-[var(--brand-primary)]/25 animate-in fade-in duration-700"
        style={{ animationDelay: "1200ms", animationFillMode: "both" }}
      >
        Let&rsquo;s go
      </button>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// Main Onboarding Page
// ═══════════════════════════════════════════════════════════════════════════

export const OnboardingPage: React.FC = () => {
  const step = useStore((s) => s.onboardingStep);
  const setStep = useStore((s) => s.setOnboardingStep);
  const setOnboardingComplete = useStore((s) => s.setOnboardingComplete);
  const setGoogleConnected = useStore((s) => s.setGoogleConnected);
  const setOnboardingResult = useStore((s) => s.setOnboardingResult);
  const setView = useStore((s) => s.setView);

  const stepIndex =
    step === "welcome" ? 0 : step === "connect" ? 1 : step === "analyzing" ? 2 : 3;

  const handleOAuthConnected = useCallback(() => {
    setGoogleConnected(true);
    setStep("analyzing");
  }, [setGoogleConnected, setStep]);

  const handleAnalysisComplete = useCallback(
    (result: OnboardingResult) => {
      setOnboardingResult(result);
      setStep("reveal");
    },
    [setOnboardingResult, setStep],
  );

  const handleFinish = useCallback(() => {
    setOnboardingComplete(true);
    setView("home");
  }, [setOnboardingComplete, setView]);

  const handleSkipGoogle = useCallback(() => {
    setOnboardingComplete(true);
    setView("home");
  }, [setOnboardingComplete, setView]);

  return (
    <div className="relative min-h-screen bg-[var(--bg-primary)]">
      <div className="pt-8">
        <StepIndicator current={stepIndex} />
      </div>

      {step === "welcome" && <WelcomeStep onNext={() => setStep("connect")} />}
      {step === "connect" && <ConnectStep onConnected={handleOAuthConnected} onSkip={handleSkipGoogle} />}
      {step === "analyzing" && <AnalyzingStep onComplete={handleAnalysisComplete} />}
      {step === "reveal" && (
        <RevealStep
          result={useStore.getState().onboardingResult!}
          onFinish={handleFinish}
        />
      )}
    </div>
  );
};
