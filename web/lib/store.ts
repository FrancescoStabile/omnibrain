/**
 * Global state — Zustand store.
 *
 * Keeps client-side state: chat messages, proposals, active view, theme.
 * Backend data is fetched on demand and cached here.
 */

import { create } from "zustand";
import type { BriefingData, ChatMessage, OnboardingResult, Proposal, SkillInfo, Status } from "./api";

// ═══════════════════════════════════════════════════════════════════════════
// Types
// ═══════════════════════════════════════════════════════════════════════════

type View = "home" | "briefing" | "chat" | "skills" | "settings" | "onboarding";
type Theme = "dark" | "light";
type OnboardingStep = "welcome" | "connect" | "analyzing" | "reveal" | "interview";

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
  chatLoading: boolean;
  setChatLoading: (v: boolean) => void;

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
  chatLoading: false,
  setChatLoading: (chatLoading) => set({ chatLoading }),

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
  sidebarOpen: true,
  setSidebarOpen: (sidebarOpen) => set({ sidebarOpen }),

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
