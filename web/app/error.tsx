/**
 * Global error boundary — catches unhandled errors in route segments.
 */

"use client";

import { useEffect } from "react";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Log to console in development
    console.error("[GlobalError]", error);
  }, [error]);

  return (
    <div className="flex flex-col items-center justify-center min-h-screen bg-[var(--bg-primary)] text-center px-6">
      <div className="h-20 w-20 rounded-full bg-[rgba(239,68,68,0.15)] flex items-center justify-center mb-6">
        <span className="text-3xl">⚠️</span>
      </div>
      <h1 className="text-2xl font-bold text-[var(--text-primary)] mb-2">
        Something went wrong
      </h1>
      <p className="text-sm text-[var(--text-tertiary)] mb-8 max-w-md">
        An unexpected error occurred. This has been logged automatically.
      </p>
      <button
        onClick={reset}
        className="inline-flex items-center gap-2 px-6 py-2.5 rounded-[var(--radius-lg)] bg-[var(--brand-primary)] text-white text-sm font-medium hover:bg-[var(--brand-hover)] transition-colors"
      >
        Try Again
      </button>
    </div>
  );
}
