/**
 * useNavigate — wraps Zustand setView + Next.js router.push
 * so every view change also updates the URL.
 *
 * Use this instead of bare `setView()` from any component.
 */
"use client";

import { useCallback } from "react";
import { useRouter } from "next/navigation";
import { useStore, type View } from "@/lib/store";

const viewPaths: Record<View, string> = {
  home: "/",
  briefing: "/briefing",
  chat: "/chat",
  timeline: "/timeline",
  contacts: "/contacts",
  knowledge: "/knowledge",
  skills: "/skills",
  settings: "/settings",
  onboarding: "/",
};

export function useNavigate() {
  const setView = useStore((s) => s.setView);
  const router = useRouter();

  const navigate = useCallback(
    (view: View) => {
      setView(view);
      if (view !== "onboarding") {
        router.push(viewPaths[view], { scroll: false });
      }
    },
    [setView, router],
  );

  return navigate;
}
