/**
 * AppShellWrapper — client boundary that renders AppShell in the root layout.
 *
 * This ensures AppShell is mounted ONCE and persists across route navigations,
 * eliminating the flicker caused by unmounting/remounting on every page change.
 *
 * Route pages render as `children` — they contain lightweight <ViewSync />
 * components that sync the URL to the Zustand view store.
 */
"use client";

import { AppShell } from "./app-shell";

export function AppShellWrapper({ children }: { children: React.ReactNode }) {
  return (
    <AppShell>
      {children}
    </AppShell>
  );
}
