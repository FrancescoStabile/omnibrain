/**
 * Sidebar — navigation panel.
 *
 * Desktop (≥640px): collapsible sidebar pinned to left.
 * Mobile (<640px): overlay drawer from left with backdrop.
 */

"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import {
  Home,
  MessageSquare,
  Puzzle,
  Settings,
  ChevronLeft,
  ChevronRight,
  Bell,
  Zap,
  Sun,
  Menu,
  X,
} from "lucide-react";
import { useStore } from "@/lib/store";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

const navItems = [
  { id: "home" as const, label: "Home", icon: Home },
  { id: "briefing" as const, label: "Briefing", icon: Sun },
  { id: "chat" as const, label: "Chat", icon: MessageSquare },
  { id: "skills" as const, label: "Skills", icon: Puzzle },
  { id: "settings" as const, label: "Settings", icon: Settings },
];

// ═══════════════════════════════════════════════════════════════════════════
// Mobile menu button (rendered in TopBar area on mobile)
// ═══════════════════════════════════════════════════════════════════════════

export function MobileMenuButton() {
  const { sidebarOpen, setSidebarOpen } = useStore();
  return (
    <Button
      variant="icon"
      size="sm"
      className="sm:hidden"
      onClick={() => setSidebarOpen(!sidebarOpen)}
      aria-label="Open menu"
    >
      <Menu className="h-4 w-4" />
    </Button>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// Sidebar
// ═══════════════════════════════════════════════════════════════════════════

export function Sidebar() {
  const { view, setView, sidebarOpen, setSidebarOpen, proposals } = useStore();
  const router = useRouter();
  const pendingCount = proposals.filter((p) => p.status === "pending").length;

  /** View-to-path mapping for Next.js navigation */
  const viewPaths: Record<string, string> = {
    home: "/",
    briefing: "/briefing",
    chat: "/chat",
    skills: "/skills",
    settings: "/settings",
  };

  // Close mobile drawer on navigation
  const handleNav = (id: typeof navItems[number]["id"]) => {
    setView(id);
    router.push(viewPaths[id] || "/", { scroll: false });
    // On mobile, close after navigation
    if (typeof window !== "undefined" && window.innerWidth < 640) {
      setSidebarOpen(false);
    }
  };

  // Close drawer on Escape
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && sidebarOpen) {
        setSidebarOpen(false);
      }
    };
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [sidebarOpen, setSidebarOpen]);

  return (
    <>
      {/* Backdrop (mobile only) */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm sm:hidden"
          onClick={() => setSidebarOpen(false)}
          aria-hidden="true"
        />
      )}

      <aside
        className={cn(
          // Base
          "flex flex-col h-full bg-[var(--bg-secondary)] border-r border-[var(--border-subtle)]",
          "transition-all duration-200",
          // Mobile: fixed overlay drawer
          "fixed inset-y-0 left-0 z-50 w-64",
          "sm:relative sm:z-auto",
          // Mobile: slide in/out
          sidebarOpen ? "translate-x-0" : "-translate-x-full",
          // Desktop: normal behavior
          "sm:translate-x-0",
          sidebarOpen ? "sm:w-64" : "sm:w-16",
        )}
      >
        {/* ── Logo ── */}
        <div className="flex items-center gap-3 px-4 h-14 border-b border-[var(--border-subtle)]">
          <div className="h-8 w-8 rounded-[var(--radius-sm)] bg-gradient-to-br from-[#7C3AED] to-[#2563EB] flex items-center justify-center shrink-0">
            <Zap className="h-4 w-4 text-white" />
          </div>
          {sidebarOpen && (
            <span className="font-bold text-[15px] text-[var(--text-primary)]">
              OmniBrain
            </span>
          )}

          {/* Mobile: close button */}
          <Button
            variant="icon"
            size="sm"
            className="ml-auto sm:hidden"
            onClick={() => setSidebarOpen(false)}
            aria-label="Close menu"
          >
            <X className="h-4 w-4" />
          </Button>

          {/* Desktop: collapse toggle */}
          <Button
            variant="icon"
            size="sm"
            className="ml-auto hidden sm:flex"
            onClick={() => setSidebarOpen(!sidebarOpen)}
            aria-label={sidebarOpen ? "Collapse sidebar" : "Expand sidebar"}
          >
            {sidebarOpen ? (
              <ChevronLeft className="h-4 w-4" />
            ) : (
              <ChevronRight className="h-4 w-4" />
            )}
          </Button>
        </div>

        {/* ── Navigation ── */}
        <nav className="flex flex-col gap-1 p-2" aria-label="Main navigation">
          {navItems.map((item) => {
            const active = view === item.id;
            const Icon = item.icon;
            return (
              <button
                key={item.id}
                onClick={() => handleNav(item.id)}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "flex items-center gap-3 px-3 py-2 rounded-[var(--radius-sm)] text-sm font-medium",
                  "transition-colors duration-100",
                  active
                    ? "bg-[var(--brand-glow)] text-[var(--brand-primary)]"
                    : "text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)]",
                  !sidebarOpen && "sm:justify-center sm:px-0",
                )}
                title={item.label}
              >
                <Icon className="h-[18px] w-[18px] shrink-0" />
                {/* Always show labels on mobile (drawer is always full-width), conditional on desktop */}
                <span className={cn(!sidebarOpen && "sm:hidden")}>
                  {item.label}
                </span>
                {item.id === "home" && pendingCount > 0 && (
                  <span className={cn(
                    "ml-auto flex h-5 min-w-5 items-center justify-center rounded-full bg-[var(--brand-primary)] text-[11px] font-semibold text-white px-1.5",
                    !sidebarOpen && "sm:hidden",
                  )}>
                    {pendingCount}
                  </span>
                )}
              </button>
            );
          })}
        </nav>

        {/* ── Proactive alerts summary ── */}
        {pendingCount > 0 && (
          <div className={cn(
            "mt-auto p-3 border-t border-[var(--border-subtle)]",
            !sidebarOpen && "sm:hidden",
          )}>
            <button
              onClick={() => handleNav("home")}
              className="flex items-center gap-2 text-sm text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors w-full"
            >
              <Bell className="h-4 w-4 text-[var(--warning)]" />
              <span>
                {pendingCount} pending{" "}
                {pendingCount === 1 ? "proposal" : "proposals"}
              </span>
            </button>
          </div>
        )}
      </aside>
    </>
  );
}
