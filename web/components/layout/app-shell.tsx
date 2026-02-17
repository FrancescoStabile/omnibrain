/**
 * AppShell — root layout with sidebar + main area.
 * Renders the active view based on store state.
 * Shows Onboarding flow for first-time users.
 * Supports deep-linking via initialView prop from route pages.
 */

"use client";

import { useEffect, useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import { Sidebar } from "./sidebar";
import { TopBar } from "./top-bar";
import { HomePage } from "@/components/views/home";
import { BriefingPage } from "@/components/views/briefing";
import { ChatPage } from "@/components/views/chat";
import { SkillsPage } from "@/components/views/skills";
import { SettingsPage } from "@/components/views/settings";
import { OnboardingPage } from "@/components/views/onboarding";
import { api } from "@/lib/api";
import { useStore, type View } from "@/lib/store";
import { ToastProvider, useToast } from "@/components/ui/toast";
import { ErrorBoundary } from "@/components/ui/error-boundary";
import { useWebSocket, setWebSocketToastFn } from "@/hooks/useWebSocket";

const views: Record<string, React.FC> = {
  home: HomePage,
  briefing: BriefingPage,
  chat: ChatPage,
  skills: SkillsPage,
  settings: SettingsPage,
  onboarding: OnboardingPage,
};

/** Map URL pathname to view name */
const pathToView: Record<string, View> = {
  "/": "home",
  "/chat": "chat",
  "/briefing": "briefing",
  "/skills": "skills",
  "/settings": "settings",
};

/** Map view name to URL pathname */
const viewToPath: Record<View, string> = {
  home: "/",
  briefing: "/briefing",
  chat: "/chat",
  skills: "/skills",
  settings: "/settings",
  onboarding: "/",
};

interface AppShellProps {
  initialView?: View;
}

/**
 * ToastBridge — connects WebSocket notifications to the toast system.
 * Must be rendered inside <ToastProvider>.
 */
function ToastBridge() {
  const toast = useToast();

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

  // Request browser notification permission (once)
  useEffect(() => {
    if (typeof Notification !== "undefined" && Notification.permission === "default") {
      Notification.requestPermission();
    }
  }, []);

  return null;
}

export function AppShell({ initialView }: AppShellProps) {
  const view = useStore((s) => s.view);
  const setView = useStore((s) => s.setView);
  const onboardingComplete = useStore((s) => s.onboardingComplete);
  const setOnboardingComplete = useStore((s) => s.setOnboardingComplete);
  const setGoogleConnected = useStore((s) => s.setGoogleConnected);
  const setOnboardingStep = useStore((s) => s.setOnboardingStep);
  const [ready, setReady] = useState(false);
  const router = useRouter();
  const pathname = usePathname();

  // ── WebSocket for real-time proactive notifications ──
  useWebSocket();

  // Sync initial view from route on mount
  useEffect(() => {
    if (initialView && initialView !== view) {
      setView(initialView);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialView]);

  // Sync URL when view changes (only if different from current path)
  useEffect(() => {
    if (!ready) return;
    if (view === "onboarding") return;
    const targetPath = viewToPath[view] || "/";
    if (pathname !== targetPath) {
      router.push(targetPath, { scroll: false });
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, ready]);

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
    // Brief loading — prevents flash of wrong view
    return (
      <div className="flex h-screen items-center justify-center bg-[var(--bg-primary)]">
        <div className="w-8 h-8 rounded-full border-2 border-[var(--brand-primary)] border-t-transparent animate-spin" />
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
