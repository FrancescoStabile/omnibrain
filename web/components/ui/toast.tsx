/**
 * Toast — lightweight notification system.
 *
 * Usage:
 *   import { ToastProvider, useToast } from "@/components/ui/toast";
 *
 *   // In layout:
 *   <ToastProvider />
 *
 *   // In any component:
 *   const toast = useToast();
 *   toast.success("Saved!");
 *   toast.error("Failed to connect.");
 *   toast.info("Syncing...");
 */

"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { Check, X, AlertTriangle, Info } from "lucide-react";
import { cn } from "@/lib/utils";

// ═══════════════════════════════════════════════════════════════════════════
// Types
// ═══════════════════════════════════════════════════════════════════════════

type ToastVariant = "success" | "error" | "warning" | "info";

interface Toast {
  id: string;
  message: string;
  variant: ToastVariant;
  duration: number;
  exiting: boolean;
}

interface ToastContextValue {
  success: (message: string, duration?: number) => void;
  error: (message: string, duration?: number) => void;
  warning: (message: string, duration?: number) => void;
  info: (message: string, duration?: number) => void;
}

// ═══════════════════════════════════════════════════════════════════════════
// Context
// ═══════════════════════════════════════════════════════════════════════════

const ToastContext = createContext<ToastContextValue | null>(null);

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within <ToastProvider>");
  return ctx;
}

// ═══════════════════════════════════════════════════════════════════════════
// Icons
// ═══════════════════════════════════════════════════════════════════════════

const icons: Record<ToastVariant, typeof Check> = {
  success: Check,
  error: X,
  warning: AlertTriangle,
  info: Info,
};

const variantStyles: Record<ToastVariant, string> = {
  success: "border-l-[var(--success)] text-[var(--success)]",
  error: "border-l-[var(--error)] text-[var(--error)]",
  warning: "border-l-[var(--warning)] text-[var(--warning)]",
  info: "border-l-[var(--info)] text-[var(--info)]",
};

// ═══════════════════════════════════════════════════════════════════════════
// Toast Item
// ═══════════════════════════════════════════════════════════════════════════

function ToastItem({
  toast,
  onDismiss,
}: {
  toast: Toast;
  onDismiss: (id: string) => void;
}) {
  const Icon = icons[toast.variant];

  return (
    <div
      role="status"
      aria-live="polite"
      className={cn(
        "flex items-center gap-3 px-4 py-3 min-w-[280px] max-w-[420px]",
        "rounded-[var(--radius-md)] shadow-[var(--shadow-lg)]",
        "bg-[var(--bg-elevated)] border border-[var(--border-default)] border-l-[3px]",
        variantStyles[toast.variant],
        toast.exiting ? "animate-toast-exit" : "animate-toast-enter",
      )}
    >
      <Icon className="h-4 w-4 shrink-0" />
      <span className="flex-1 text-sm text-[var(--text-primary)]">
        {toast.message}
      </span>
      <button
        onClick={() => onDismiss(toast.id)}
        className="shrink-0 text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] transition-colors"
        aria-label="Dismiss notification"
      >
        <X className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// Provider
// ═══════════════════════════════════════════════════════════════════════════

export function ToastProvider({ children }: { children?: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const timers = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());

  const dismiss = useCallback((id: string) => {
    // Start exit animation
    setToasts((prev) =>
      prev.map((t) => (t.id === id ? { ...t, exiting: true } : t)),
    );
    // Remove after animation
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 200);
  }, []);

  const add = useCallback(
    (variant: ToastVariant, message: string, duration = 4000) => {
      const id = `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
      const toast: Toast = { id, message, variant, duration, exiting: false };
      setToasts((prev) => [...prev.slice(-4), toast]); // Max 5 visible

      const timer = setTimeout(() => dismiss(id), duration);
      timers.current.set(id, timer);

      return id;
    },
    [dismiss],
  );

  // Clean up timers
  useEffect(() => {
    return () => {
      timers.current.forEach((t) => clearTimeout(t));
    };
  }, []);

  const ctx: ToastContextValue = {
    success: (msg, dur) => add("success", msg, dur),
    error: (msg, dur) => add("error", msg, dur),
    warning: (msg, dur) => add("warning", msg, dur),
    info: (msg, dur) => add("info", msg, dur),
  };

  return (
    <ToastContext.Provider value={ctx}>
      {children}
      {/* Toast container — fixed bottom-right */}
      {toasts.length > 0 && (
        <div
          aria-label="Notifications"
          className="fixed bottom-6 right-6 z-50 flex flex-col-reverse gap-2 pointer-events-auto"
        >
          {toasts.map((t) => (
            <ToastItem key={t.id} toast={t} onDismiss={dismiss} />
          ))}
        </div>
      )}
    </ToastContext.Provider>
  );
}
