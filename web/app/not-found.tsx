/**
 * 404 — branded page for routes that don't exist.
 */

import Link from "next/link";

export default function NotFound() {
  return (
    <div className="flex flex-col items-center justify-center min-h-screen bg-[var(--bg-primary)] text-center px-6">
      <div className="h-20 w-20 rounded-full bg-[var(--brand-glow)] flex items-center justify-center mb-6">
        <span className="text-4xl font-bold text-[var(--brand-primary)]">404</span>
      </div>
      <h1 className="text-2xl font-bold text-[var(--text-primary)] mb-2">
        Page not found
      </h1>
      <p className="text-sm text-[var(--text-tertiary)] mb-8 max-w-md">
        The page you&apos;re looking for doesn&apos;t exist or has been moved.
      </p>
      <Link
        href="/"
        className="inline-flex items-center gap-2 px-6 py-2.5 rounded-[var(--radius-lg)] bg-[var(--brand-primary)] text-white text-sm font-medium hover:bg-[var(--brand-hover)] transition-colors"
      >
        Go Home
      </Link>
    </div>
  );
}
