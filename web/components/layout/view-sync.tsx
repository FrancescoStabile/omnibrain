/**
 * ViewSync — lightweight client component that syncs
 * the URL-based route to the Zustand view store.
 *
 * This is rendered as `children` inside the root layout's AppShell,
 * so the AppShell itself never unmounts during navigation (no flicker).
 */
"use client";

import { useEffect } from "react";
import { usePathname } from "next/navigation";
import { useStore, type View } from "@/lib/store";

const pathToView: Record<string, View> = {
  "/": "home",
  "/chat": "chat",
  "/briefing": "briefing",
  "/timeline": "timeline",
  "/contacts": "contacts",
  "/knowledge": "knowledge",
  "/skills": "skills",
  "/settings": "settings",
  "/transparency": "transparency",
};

export function ViewSync() {
  const pathname = usePathname();
  const setView = useStore((s) => s.setView);
  const onboardingComplete = useStore((s) => s.onboardingComplete);

  useEffect(() => {
    // Don't override onboarding
    if (!onboardingComplete) return;
    const target = pathToView[pathname];
    if (target) {
      setView(target);
    }
  }, [pathname, setView, onboardingComplete]);

  return null;
}
