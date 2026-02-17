/**
 * useHotkeys — global keyboard shortcuts.
 *
 * Listens for keydown events and dispatches navigation + actions.
 * Shortcuts are disabled when an input/textarea is focused.
 */

"use client";

import { useEffect, useCallback, useState } from "react";
import { useStore } from "@/lib/store";

interface ShortcutDef {
  key: string;
  ctrl?: boolean;
  meta?: boolean; // Cmd on macOS
  shift?: boolean;
  label: string;
  action: () => void;
}

export function useHotkeys() {
  const setView = useStore((s) => s.setView);

  const shortcuts: ShortcutDef[] = [
    // Navigation
    { key: "1", meta: true, label: "Go to Home", action: () => setView("home") },
    { key: "2", meta: true, label: "Go to Briefing", action: () => setView("briefing") },
    { key: "3", meta: true, label: "Go to Chat", action: () => setView("chat") },
    { key: "4", meta: true, label: "Go to Skills", action: () => setView("skills") },
    { key: "5", meta: true, label: "Go to Settings", action: () => setView("settings") },
  ];

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      // Don't fire when typing in an input, textarea, or contenteditable
      const tag = (e.target as HTMLElement)?.tagName;
      const isEditable =
        tag === "INPUT" || tag === "TEXTAREA" || (e.target as HTMLElement)?.isContentEditable;
      if (isEditable) return;

      // Match Ctrl or Cmd (Meta)
      const mod = e.ctrlKey || e.metaKey;

      for (const s of shortcuts) {
        const needsMod = s.ctrl || s.meta;
        if (needsMod && !mod) continue;
        if (!needsMod && mod) continue;
        if (s.shift && !e.shiftKey) continue;
        if (e.key.toLowerCase() === s.key.toLowerCase()) {
          e.preventDefault();
          s.action();
          return;
        }
      }

      // Slash key → focus chat input (when not editing)
      if (e.key === "/" && !mod && !isEditable) {
        e.preventDefault();
        const chatInput = document.querySelector<HTMLInputElement>(
          'input[placeholder="Ask me anything..."]',
        );
        if (chatInput) {
          chatInput.focus();
        } else {
          setView("chat");
        }
      }

      // ? key → toggle shortcut help
      if (e.key === "?" && e.shiftKey && !isEditable) {
        e.preventDefault();
        const helpEvent = new CustomEvent("omnibrain:toggle-shortcuts-help");
        window.dispatchEvent(helpEvent);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [setView],
  );

  useEffect(() => {
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [handleKeyDown]);

  return shortcuts;
}

/**
 * ShortcutsHelp — floating modal showing available shortcuts.
 * Toggle with Shift+?
 */
export function ShortcutsHelp() {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const handler = () => setOpen((v) => !v);
    window.addEventListener("omnibrain:toggle-shortcuts-help", handler);
    return () => window.removeEventListener("omnibrain:toggle-shortcuts-help", handler);
  }, []);

  // Close on Escape
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open]);

  if (!open) return null;

  const isMac = typeof navigator !== "undefined" && /Mac|iPhone/.test(navigator.userAgent);
  const mod = isMac ? "⌘" : "Ctrl+";

  const groups = [
    {
      title: "Navigation",
      shortcuts: [
        { keys: `${mod}1`, label: "Home" },
        { keys: `${mod}2`, label: "Briefing" },
        { keys: `${mod}3`, label: "Chat" },
        { keys: `${mod}4`, label: "Skills" },
        { keys: `${mod}5`, label: "Settings" },
      ],
    },
    {
      title: "Actions",
      shortcuts: [
        { keys: "/", label: "Focus chat input" },
        { keys: "?", label: "Toggle this help" },
        { keys: "Esc", label: "Close panel / dialog" },
      ],
    },
  ];

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-[90] bg-black/50 animate-[fade-in_150ms_ease-out]"
        onClick={() => setOpen(false)}
      />
      {/* Modal */}
      <div
        role="dialog"
        aria-label="Keyboard shortcuts"
        className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-[91] w-[360px] max-w-[90vw] p-6 rounded-2xl bg-[var(--bg-elevated)] border border-[var(--border-default)] shadow-xl animate-[slide-up_200ms_ease-out]"
      >
        <h2 className="text-lg font-bold text-[var(--text-primary)] mb-4">
          Keyboard Shortcuts
        </h2>
        {groups.map((group) => (
          <div key={group.title} className="mb-4 last:mb-0">
            <h3 className="text-xs font-medium text-[var(--text-tertiary)] uppercase tracking-wider mb-2">
              {group.title}
            </h3>
            <div className="space-y-1.5">
              {group.shortcuts.map((s) => (
                <div key={s.keys} className="flex items-center justify-between">
                  <span className="text-sm text-[var(--text-secondary)]">{s.label}</span>
                  <kbd className="px-2 py-0.5 rounded bg-[var(--bg-tertiary)] border border-[var(--border-subtle)] text-xs font-mono text-[var(--text-primary)]">
                    {s.keys}
                  </kbd>
                </div>
              ))}
            </div>
          </div>
        ))}
        <p className="text-xs text-[var(--text-tertiary)] mt-4 text-center">
          Press <kbd className="px-1 py-0.5 rounded bg-[var(--bg-tertiary)] text-[10px] font-mono">Esc</kbd> to close
        </p>
      </div>
    </>
  );
}
