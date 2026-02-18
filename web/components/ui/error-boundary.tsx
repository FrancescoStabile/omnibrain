/**
 * ErrorBoundary — catches React render errors and shows a recovery UI.
 *
 * Wraps content areas so a crash in one view doesn't take down the whole app.
 * Provides contextual recovery guidance based on error patterns:
 * - Network/fetch errors → "Backend not running" hint
 * - OAuth errors → "Connect Google account" guidance
 * - API key errors → "Add API key in Settings" guidance
 * - Generic → retry button
 */

"use client";

import { Component, type ErrorInfo, type ReactNode } from "react";
import { AlertTriangle, Key, LinkIcon, RefreshCw, WifiOff } from "lucide-react";
import { Button } from "@/components/ui/button";

interface Props {
  children: ReactNode;
  /** Optional fallback component */
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

/**
 * Classify a render error into a recovery category.
 */
function classifyError(error: Error | null): {
  icon: ReactNode;
  title: string;
  description: string;
  hint?: ReactNode;
} {
  const msg = (error?.message || "").toLowerCase();

  if (
    msg.includes("network") ||
    msg.includes("fetch") ||
    msg.includes("failed to fetch") ||
    msg.includes("backend") ||
    msg.includes("econnrefused")
  ) {
    return {
      icon: <WifiOff className="h-7 w-7 text-[var(--error)]" />,
      title: "Backend not reachable",
      description: "OmniBrain's backend isn't responding. Make sure it's running:",
      hint: (
        <code className="block mt-2 text-xs font-mono bg-[var(--bg-tertiary)] text-[var(--text-secondary)] px-3 py-2 rounded-[var(--radius-sm)]">
          docker compose up -d
        </code>
      ),
    };
  }

  if (msg.includes("oauth") || msg.includes("google")) {
    return {
      icon: <LinkIcon className="h-7 w-7 text-[var(--error)]" />,
      title: "Google account not connected",
      description:
        "This feature requires a connected Google account. Go to Settings to connect.",
    };
  }

  if (msg.includes("api key") || msg.includes("apikey") || msg.includes("unauthorized")) {
    return {
      icon: <Key className="h-7 w-7 text-[var(--error)]" />,
      title: "No API key configured",
      description:
        "Add an LLM API key in Settings → LLM so OmniBrain can work.",
    };
  }

  return {
    icon: <AlertTriangle className="h-7 w-7 text-[var(--error)]" />,
    title: "Something went wrong",
    description: error?.message || "An unexpected error occurred.",
  };
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("[ErrorBoundary] Caught:", error, info.componentStack);
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;

      const classified = classifyError(this.state.error);

      return (
        <div
          role="alert"
          className="flex flex-col items-center justify-center gap-4 p-8 text-center min-h-[300px]"
        >
          <div className="flex h-14 w-14 items-center justify-center rounded-full bg-[rgba(239,68,68,0.1)]">
            {classified.icon}
          </div>
          <div className="space-y-1.5">
            <h2 className="text-lg font-semibold text-[var(--text-primary)]">
              {classified.title}
            </h2>
            <p className="text-sm text-[var(--text-tertiary)] max-w-sm">
              {classified.description}
            </p>
            {classified.hint}
          </div>
          <Button variant="secondary" size="md" onClick={this.handleRetry}>
            <RefreshCw className="h-4 w-4" />
            Try Again
          </Button>
        </div>
      );
    }

    return this.props.children;
  }
}
