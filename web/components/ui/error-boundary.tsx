/**
 * ErrorBoundary — catches React render errors and shows a recovery UI.
 *
 * Wraps content areas so a crash in one view doesn't take down the whole app.
 * Provides a retry mechanism and optional toast notification.
 */

"use client";

import { Component, type ErrorInfo, type ReactNode } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";
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

      return (
        <div
          role="alert"
          className="flex flex-col items-center justify-center gap-4 p-8 text-center min-h-[300px]"
        >
          <div className="flex h-14 w-14 items-center justify-center rounded-full bg-[rgba(239,68,68,0.1)]">
            <AlertTriangle className="h-7 w-7 text-[var(--error)]" />
          </div>
          <div className="space-y-1.5">
            <h2 className="text-lg font-semibold text-[var(--text-primary)]">
              Something went wrong
            </h2>
            <p className="text-sm text-[var(--text-tertiary)] max-w-sm">
              {this.state.error?.message || "An unexpected error occurred."}
            </p>
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
