/**
 * AppShell — root layout with sidebar + main area.
 * Renders the active view based on store state.
 * Shows Onboarding flow for first-time users.
 * Supports deep-linking via initialView prop from route pages.
 */

"use client";

import { useEffect, useState } from "react";
import { Sidebar } from "./sidebar";
import { TopBar } from "./top-bar";
import { HomePage } from "@/components/views/home";
import { BriefingPage } from "@/components/views/briefing";
import { ChatPage } from "@/components/views/chat";
import { SkillsPage } from "@/components/views/skills";
import { SettingsPage } from "@/components/views/settings";
import { OnboardingPage } from "@/components/views/onboarding";
import { TimelinePage } from "@/components/views/timeline";
import { ContactsPage } from "@/components/views/contacts";
import { KnowledgePage } from "@/components/views/knowledge";
import { TransparencyPage } from "@/components/views/transparency";
import { api, ApiError, setApiErrorHandler } from "@/lib/api";
import { useStore, type View } from "@/lib/store";
import { ToastProvider, useToast } from "@/components/ui/toast";
import { ErrorBoundary } from "@/components/ui/error-boundary";
import { useWebSocket, setWebSocketToastFn } from "@/hooks/useWebSocket";
import { useHotkeys, ShortcutsHelp } from "@/hooks/useHotkeys";
import { useOnlineStatus } from "@/hooks/useOnlineStatus";

const views: Record<string, React.FC> = {
  home: HomePage,
  briefing: BriefingPage,
  chat: ChatPage,
  timeline: TimelinePage,
  contacts: ContactsPage,
  knowledge: KnowledgePage,
  skills: SkillsPage,
  settings: SettingsPage,
  onboarding: OnboardingPage,
  transparency: TransparencyPage,
};

interface AppShellProps {
  children?: React.ReactNode;
}

/**
 * ToastBridge — connects WebSocket notifications to the toast system.
 * Must be rendered inside <ToastProvider>.
 */
function ToastBridge() {
  const toast = useToast();
  const online = useOnlineStatus();

  // Wire WebSocket notifications to toast
  useEffect(() => {
    setWebSocketToastFn((level: string, message: string) => {
      if (level === "critical") {
        toast.error(message, 8000);
      } else if (level === "important") {
        toast.warning(message, 6000);
      } else {
        toast.info(message, 4000);
      }
    });
    return () => setWebSocketToastFn(null);
  }, [toast]);

  // Wire global API errors to toast — suppress when offline
  useEffect(() => {
    setApiErrorHandler((err: ApiError) => {
      if (!navigator.onLine) return; // Suppress individual errors when offline
      switch (err.kind) {
        case "backend_down":
          toast.error("Backend not reachable — is OmniBrain running?", 6000);
          break;
        case "google_disconnected":
          toast.warning("Google account not connected. Go to Settings to connect.", 5000);
          break;
        case "no_api_key":
          toast.warning("No API key configured. Add one in Settings → LLM.", 5000);
          break;
        case "rate_limited":
          toast.warning("Too many requests — slow down a bit.", 4000);
          break;
        case "server_error":
          toast.error(`Server error: ${err.message}`, 5000);
          break;
        // 4xx / not_found / generic — typically handled by calling component
        default:
          break;
      }
    });
    return () => setApiErrorHandler(null);
  }, [toast]);

  // Auto-refresh data when coming back online
  useEffect(() => {
    if (online) {
      // Small delay to let network stabilize
      const t = setTimeout(() => {
        const { setBriefingData, setBriefingLoading, setProposals, setStatus } = useStore.getState();
        Promise.allSettled([
          api.getBriefingData().then(setBriefingData),
          api.getProposals().then(setProposals),
          api.getStatus().then(setStatus),
        ]).catch(() => {});
      }, 1000);
      return () => clearTimeout(t);
    }
  }, [online]);

  // Request browser notification permission (once)
  useEffect(() => {
    if (typeof Notification !== "undefined" && Notification.permission === "default") {
      Notification.requestPermission();
    }
  }, []);

  return null;
}

export function AppShell({ children }: AppShellProps) {
  const view = useStore((s) => s.view);
  const setView = useStore((s) => s.setView);
  const onboardingComplete = useStore((s) => s.onboardingComplete);
  const setOnboardingComplete = useStore((s) => s.setOnboardingComplete);
  const setGoogleConnected = useStore((s) => s.setGoogleConnected);
  const setOnboardingStep = useStore((s) => s.setOnboardingStep);
  const [ready, setReady] = useState(false);

  // ── WebSocket for real-time proactive notifications ──
  useWebSocket();

  // ── Global keyboard shortcuts ──
  useHotkeys();

  // Apply persisted theme on first render
  useEffect(() => {
    const theme = useStore.getState().theme;
    document.documentElement.setAttribute("data-theme", theme);
  }, []);

  // On mount: check OAuth status to decide whether to show onboarding
  useEffect(() => {
    // Check URL for OAuth callback
    const params = new URLSearchParams(window.location.search);
    if (params.get("oauth") === "success") {
      setGoogleConnected(true);
      setOnboardingStep("analyzing");
      setView("onboarding");
      setReady(true);
      return;
    }

    // Already completed onboarding (persisted in localStorage)
    if (useStore.getState().onboardingComplete) {
      setReady(true);
      return;
    }

    // Check backend: if user has a name in settings, they already onboarded
    Promise.all([
      api.getOAuthStatus().catch(() => ({ connected: false })),
      api.getSettings().catch(() => null),
    ]).then(([oauthStatus, settings]) => {
      if (oauthStatus.connected) {
        setGoogleConnected(true);
        setOnboardingComplete(true);
      } else if (settings?.profile?.name) {
        // User completed interview-based onboarding previously
        setOnboardingComplete(true);
      } else {
        // First time: show onboarding
        setView("onboarding");
      }
    }).catch(() => {
      // Backend unreachable — skip onboarding, show home
      setOnboardingComplete(true);
    }).finally(() => setReady(true));
  }, [setView, setOnboardingComplete, setGoogleConnected, setOnboardingStep]);

  if (!ready) {
    // Skeleton loading — matches shell layout for seamless transition
    return (
      <div className="flex h-screen bg-[var(--bg-primary)]">
        {/* Sidebar skeleton */}
        <div className="hidden md:flex w-[220px] flex-col border-r border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-4 gap-4">
          <div className="h-8 w-24 rounded-[var(--radius-md)] bg-[var(--bg-tertiary)] animate-skeleton" />
          <div className="space-y-2 mt-4">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="h-8 rounded-[var(--radius-md)] bg-[var(--bg-tertiary)] animate-skeleton" style={{ animationDelay: `${i * 100}ms` }} />
            ))}
          </div>
        </div>
        {/* Main content skeleton */}
        <div className="flex-1 flex flex-col">
          {/* TopBar skeleton */}
          <div className="h-14 border-b border-[var(--border-subtle)] flex items-center px-6">
            <div className="h-5 w-32 rounded bg-[var(--bg-tertiary)] animate-skeleton" />
            <div className="ml-auto flex gap-3">
              <div className="h-8 w-8 rounded-full bg-[var(--bg-tertiary)] animate-skeleton" />
              <div className="h-8 w-8 rounded-full bg-[var(--bg-tertiary)] animate-skeleton" />
            </div>
          </div>
          {/* Content skeleton */}
          <div className="flex-1 p-6 max-w-3xl mx-auto w-full space-y-4">
            <div className="h-10 w-64 rounded-[var(--radius-md)] bg-[var(--bg-tertiary)] animate-skeleton" />
            <div className="h-5 w-40 rounded bg-[var(--bg-tertiary)] animate-skeleton" />
            <div className="mt-6 space-y-3">
              {Array.from({ length: 3 }).map((_, i) => (
                <div key={i} className="h-24 rounded-[var(--radius-lg)] bg-[var(--bg-tertiary)] animate-skeleton" style={{ animationDelay: `${i * 150}ms` }} />
              ))}
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Onboarding: full-screen, no sidebar
  if (view === "onboarding" && !onboardingComplete) {
    return (
      <ToastProvider>
        <OnboardingPage />
      </ToastProvider>
    );
  }

  const ActiveView = views[view] || HomePage;

  return (
    <ToastProvider>
      <ToastBridge />
      <ShortcutsHelp />
      {/* ViewSync from route pages — syncs URL→store, renders nothing */}
      {children}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-[100] focus:px-4 focus:py-2 focus:rounded-[var(--radius-sm)] focus:bg-[var(--brand-primary)] focus:text-white focus:text-sm focus:font-medium"
      >
        Skip to content
      </a>
      <div className="flex h-screen overflow-hidden">
        <Sidebar />
        <div className="flex flex-col flex-1 overflow-hidden">
          <TopBar />
          <main id="main-content" className="flex-1 overflow-y-auto">
            <ErrorBoundary>
              <ActiveView />
            </ErrorBoundary>
          </main>
        </div>
      </div>
    </ToastProvider>
  );
}
