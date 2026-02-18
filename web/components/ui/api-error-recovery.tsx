/**
 * ApiErrorRecovery — contextual error display with recovery actions.
 *
 * Classifies API errors and shows targeted guidance:
 * - Backend down → "Start OmniBrain: docker compose up"
 * - Google disconnected → "Connect your Google account" button
 * - No API key → "Add an API key in Settings → LLM"
 * - Server error → retry
 * - Rate limited → wait message
 * - Generic → retry
 */

"use client";

import {
  AlertTriangle,
  Cloud,
  Key,
  LinkIcon,
  RefreshCw,
  Timer,
  WifiOff,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";
import { type ApiError, type ErrorKind } from "@/lib/api";
import { useStore } from "@/lib/store";

// ═══════════════════════════════════════════════════════════════════════════
// Error recovery configs
// ═══════════════════════════════════════════════════════════════════════════

interface RecoveryConfig {
  icon: React.ReactNode;
  title: string;
  description: string;
  action?: {
    label: string;
    /** "retry" calls onRetry, "navigate:view" navigates to a view */
    type: "retry" | `navigate:${string}`;
  };
}

const recoveryMap: Record<ErrorKind, RecoveryConfig> = {
  backend_down: {
    icon: <WifiOff className="h-6 w-6" />,
    title: "Backend not reachable",
    description:
      "OmniBrain's backend isn't responding. Make sure it's running:",
    action: { label: "Try Again", type: "retry" },
  },
  google_disconnected: {
    icon: <LinkIcon className="h-6 w-6" />,
    title: "Google account not connected",
    description:
      "Connect your Google account to unlock email and calendar intelligence.",
    action: { label: "Connect Google Account", type: "navigate:settings" },
  },
  no_api_key: {
    icon: <Key className="h-6 w-6" />,
    title: "No API key configured",
    description:
      "Add an LLM API key so OmniBrain can think. Go to Settings → LLM to add one.",
    action: { label: "Go to Settings", type: "navigate:settings" },
  },
  rate_limited: {
    icon: <Timer className="h-6 w-6" />,
    title: "Too many requests",
    description:
      "You're sending requests too fast. Wait a moment and try again.",
    action: { label: "Try Again", type: "retry" },
  },
  server_error: {
    icon: <Cloud className="h-6 w-6" />,
    title: "Server error",
    description:
      "Something went wrong on the server side. This is usually temporary.",
    action: { label: "Try Again", type: "retry" },
  },
  not_found: {
    icon: <AlertTriangle className="h-6 w-6" />,
    title: "Not found",
    description: "The requested resource doesn't exist or hasn't been created yet.",
    action: { label: "Try Again", type: "retry" },
  },
  generic: {
    icon: <AlertTriangle className="h-6 w-6" />,
    title: "Something went wrong",
    description: "An unexpected error occurred.",
    action: { label: "Try Again", type: "retry" },
  },
};

// ═══════════════════════════════════════════════════════════════════════════
// Component
// ═══════════════════════════════════════════════════════════════════════════

interface ApiErrorRecoveryProps {
  /** The API error, or a pre-classified ErrorKind string */
  error: ApiError | ErrorKind | string;
  /** Called when the user clicks "Try Again" */
  onRetry?: () => void;
  /** Compact mode — inline rather than card */
  compact?: boolean;
  /** Additional class names */
  className?: string;
}

export function ApiErrorRecovery({
  error,
  onRetry,
  compact = false,
  className = "",
}: ApiErrorRecoveryProps) {
  const setView = useStore((s) => s.setView);

  // Resolve the error kind
  let kind: ErrorKind;
  let rawMessage: string | undefined;

  if (typeof error === "string") {
    // Check if it's a known ErrorKind
    if (error in recoveryMap) {
      kind = error as ErrorKind;
    } else {
      // Heuristic classification from plain error messages
      const lower = error.toLowerCase();
      if (lower.includes("backend") || lower.includes("network") || lower.includes("unreachable")) {
        kind = "backend_down";
      } else if (lower.includes("google") || lower.includes("oauth")) {
        kind = "google_disconnected";
      } else if (lower.includes("api key") || lower.includes("apikey")) {
        kind = "no_api_key";
      } else {
        kind = "generic";
      }
      rawMessage = error;
    }
  } else {
    // It's an ApiError instance with .kind
    kind = error.kind;
    rawMessage = error.message;
  }

  const config = recoveryMap[kind];

  const handleAction = () => {
    if (!config.action) return;
    if (config.action.type === "retry") {
      onRetry?.();
    } else if (config.action.type.startsWith("navigate:")) {
      const view = config.action.type.split(":")[1];
      setView(view as Parameters<typeof setView>[0]);
    }
  };

  // ── Compact mode — single line with retry ──
  if (compact) {
    return (
      <div className={`flex items-center gap-3 px-3 py-2 rounded-[var(--radius-md)] bg-[rgba(239,68,68,0.06)] ${className}`}>
        <span className="text-[var(--error)] shrink-0">{config.icon}</span>
        <span className="text-sm text-[var(--text-secondary)] flex-1">
          {rawMessage || config.description}
        </span>
        {config.action && (
          <Button variant="ghost" size="sm" onClick={handleAction}>
            {config.action.type === "retry" && <RefreshCw className="h-3.5 w-3.5 mr-1" />}
            {config.action.label}
          </Button>
        )}
      </div>
    );
  }

  // ── Full mode — centered card ──
  return (
    <Card className={className}>
      <CardBody className="flex flex-col items-center justify-center gap-4 py-10 text-center">
        <div className="flex h-14 w-14 items-center justify-center rounded-full bg-[rgba(239,68,68,0.08)]">
          <span className="text-[var(--error)]">{config.icon}</span>
        </div>
        <div className="space-y-1.5 max-w-sm">
          <h3 className="text-base font-semibold text-[var(--text-primary)]">
            {config.title}
          </h3>
          <p className="text-sm text-[var(--text-tertiary)]">
            {config.description}
          </p>
          {/* Show terminal command hint for backend_down */}
          {kind === "backend_down" && (
            <code className="block mt-2 text-xs font-mono bg-[var(--bg-tertiary)] text-[var(--text-secondary)] px-3 py-2 rounded-[var(--radius-sm)]">
              docker compose up -d
            </code>
          )}
          {/* Show raw error detail if different from description */}
          {rawMessage && rawMessage !== config.description && (
            <p className="text-xs text-[var(--text-tertiary)] mt-1 opacity-60">
              {rawMessage}
            </p>
          )}
        </div>
        {config.action && (
          <Button
            variant={config.action.type === "retry" ? "secondary" : "primary"}
            size="md"
            onClick={handleAction}
          >
            {config.action.type === "retry" && <RefreshCw className="h-4 w-4 mr-1.5" />}
            {config.action.label}
          </Button>
        )}
      </CardBody>
    </Card>
  );
}
