/**
 * Skeleton — loading placeholder with pulse animation.
 */

import { cn } from "@/lib/utils";

export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        "rounded-[var(--radius-md)] bg-[var(--bg-tertiary)] animate-[skeleton-pulse_1.5s_ease-in-out_infinite]",
        className,
      )}
    />
  );
}

export function SkeletonCard() {
  return (
    <div className="rounded-[var(--radius-md)] bg-[var(--bg-secondary)] border border-[var(--border-subtle)] p-5 space-y-3">
      <div className="flex items-center gap-3">
        <Skeleton className="h-5 w-5 rounded-full" />
        <Skeleton className="h-4 w-32" />
      </div>
      <Skeleton className="h-3 w-full" />
      <Skeleton className="h-3 w-3/4" />
    </div>
  );
}
