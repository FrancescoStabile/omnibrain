/**
 * Global state — Zustand store.
 *
 * Keeps client-side state: chat messages, proposals, active view, theme.
 * Backend data is fetched on demand and cached here.
 */

import { create } from "zustand";
import type { BriefingData, ChatMessage, ChatSession, OnboardingResult, Proposal, SkillInfo, Status } from "./api";

// ═══════════════════════════════════════════════════════════════════════════
// Types
// ═══════════════════════════════════════════════════════════════════════════

type View = "home" | "briefing" | "chat" | "timeline" | "contacts" | "knowledge" | "skills" | "settings" | "onboarding";
export type { View };
type Theme = "dark" | "light";
type OnboardingStep = "welcome" | "connect" | "analyzing" | "reveal" | "interview";

export interface ProactiveNotification {
  id: string;
  level: string;
  title: string;
  message: string;
  timestamp: string;
}

interface AppState {
  // ── Navigation ──
  view: View;
  setView: (v: View) => void;

  // ── Theme ──
  theme: Theme;
  toggleTheme: () => void;

  // ── Chat ──
  messages: ChatMessage[];
  addMessage: (msg: ChatMessage) => void;
  appendToLastAssistant: (chunk: string) => void;
  clearMessages: () => void;
  setMessages: (msgs: ChatMessage[]) => void;
  chatLoading: boolean;
  setChatLoading: (v: boolean) => void;
  chatSessionId: string;
  setChatSessionId: (id: string) => void;
  chatSessions: ChatSession[];
  setChatSessions: (s: ChatSession[]) => void;

  // ── Notifications (proactive) ──
  notifications: ProactiveNotification[];
  addNotification: (n: ProactiveNotification) => void;
  dismissNotification: (id: string) => void;

  // ── Proposals (proactive feed) ──
  proposals: Proposal[];
  setProposals: (p: Proposal[]) => void;
  removeProposal: (id: number) => void;

  // ── Skills ──
  skills: SkillInfo[];
  setSkills: (s: SkillInfo[]) => void;

  // ── Status ──
  status: Status | null;
  setStatus: (s: Status) => void;

  // ── Sidebar ──
  sidebarOpen: boolean;
  setSidebarOpen: (v: boolean) => void;

  // ── Briefing ──
  briefingData: BriefingData | null;
  setBriefingData: (d: BriefingData) => void;
  briefingLoading: boolean;
  setBriefingLoading: (v: boolean) => void;

  // ── Onboarding ──
  onboardingStep: OnboardingStep;
  setOnboardingStep: (step: OnboardingStep) => void;
  onboardingComplete: boolean;
  setOnboardingComplete: (v: boolean) => void;
  googleConnected: boolean;
  setGoogleConnected: (v: boolean) => void;
  onboardingResult: OnboardingResult | null;
  setOnboardingResult: (r: OnboardingResult) => void;
}

// ═══════════════════════════════════════════════════════════════════════════
// Helpers
// ═══════════════════════════════════════════════════════════════════════════

function getInitialTheme(): Theme {
  if (typeof window === "undefined") return "dark";
  try {
    const stored = localStorage.getItem("omnibrain-theme");
    if (stored === "light" || stored === "dark") return stored;
  } catch {
    // SSR or blocked storage
  }
  // Respect system preference
  if (typeof window !== "undefined" && window.matchMedia?.("(prefers-color-scheme: light)").matches) {
    return "light";
  }
  return "dark";
}

function getInitialOnboardingComplete(): boolean {
  if (typeof window === "undefined") return false;
  try {
    return localStorage.getItem("omnibrain-onboarding-complete") === "true";
  } catch {
    return false;
  }
}

function getInitialSessionId(): string {
  if (typeof window === "undefined") return "default";
  try {
    return localStorage.getItem("omnibrain-chat-session") || "default";
  } catch {
    return "default";
  }
}

function applyTheme(theme: Theme) {
  if (typeof document !== "undefined") {
    document.documentElement.setAttribute("data-theme", theme);
  }
  if (typeof window !== "undefined") {
    try {
      localStorage.setItem("omnibrain-theme", theme);
    } catch {
      // Quota or privacy mode
    }
  }
}

function getInitialSidebarOpen(): boolean {
  if (typeof window === "undefined") return true;
  try {
    const stored = localStorage.getItem("omnibrain-sidebar-open");
    if (stored !== null) return stored === "true";
  } catch { /* SSR */ }
  return window.innerWidth >= 640;
}

// ═══════════════════════════════════════════════════════════════════════════
// Store
// ═══════════════════════════════════════════════════════════════════════════

export const useStore = create<AppState>((set) => ({
  // Navigation
  view: "home",
  setView: (view) => set({ view }),

  // Theme
  theme: getInitialTheme(),
  toggleTheme: () =>
    set((s) => {
      const next = s.theme === "dark" ? "light" : "dark";
      applyTheme(next);
      return { theme: next };
    }),

  // Chat
  messages: [],
  addMessage: (msg) => set((s) => ({ messages: [...s.messages, msg] })),
  appendToLastAssistant: (chunk) =>
    set((s) => {
      const msgs = [...s.messages];
      const last = msgs[msgs.length - 1];
      if (last?.role === "assistant") {
        msgs[msgs.length - 1] = { ...last, content: last.content + chunk };
      }
      return { messages: msgs };
    }),
  clearMessages: () => set({ messages: [] }),
  setMessages: (messages) => set({ messages }),
  chatLoading: false,
  setChatLoading: (chatLoading) => set({ chatLoading }),
  chatSessionId: getInitialSessionId(),
  setChatSessionId: (chatSessionId) => {
    try {
      if (typeof window !== "undefined") {
        localStorage.setItem("omnibrain-chat-session", chatSessionId);
      }
    } catch { /* quota */ }
    set({ chatSessionId });
  },
  chatSessions: [],
  setChatSessions: (chatSessions) => set({ chatSessions }),

  // Notifications
  notifications: [],
  addNotification: (n) =>
    set((s) => ({ notifications: [n, ...s.notifications].slice(0, 50) })),
  dismissNotification: (id) =>
    set((s) => ({ notifications: s.notifications.filter((n) => n.id !== id) })),

  // Proposals
  proposals: [],
  setProposals: (proposals) => set({ proposals }),
  removeProposal: (id) =>
    set((s) => ({ proposals: s.proposals.filter((p) => p.id !== id) })),

  // Skills
  skills: [],
  setSkills: (skills) => set({ skills }),

  // Status
  status: null,
  setStatus: (status) => set({ status }),

  // Sidebar
  sidebarOpen: getInitialSidebarOpen(),
  setSidebarOpen: (sidebarOpen) => {
    try {
      if (typeof window !== "undefined") {
        localStorage.setItem("omnibrain-sidebar-open", String(sidebarOpen));
      }
    } catch { /* quota */ }
    set({ sidebarOpen });
  },

  // Briefing
  briefingData: null,
  setBriefingData: (briefingData) => set({ briefingData }),
  briefingLoading: false,
  setBriefingLoading: (briefingLoading) => set({ briefingLoading }),

  // Onboarding
  onboardingStep: "welcome",
  setOnboardingStep: (onboardingStep) => set({ onboardingStep }),
  onboardingComplete: getInitialOnboardingComplete(),
  setOnboardingComplete: (onboardingComplete) => {
    try {
      if (typeof window !== "undefined") {
        localStorage.setItem("omnibrain-onboarding-complete", String(onboardingComplete));
      }
    } catch { /* quota or private mode */ }
    set({ onboardingComplete });
  },
  googleConnected: false,
  setGoogleConnected: (googleConnected) => set({ googleConnected }),
  onboardingResult: null,
  setOnboardingResult: (onboardingResult) => set({ onboardingResult }),
}));
