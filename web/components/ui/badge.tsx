/**
 * Badge — small label for categories, statuses.
 */

import { cn } from "@/lib/utils";
import type { ReactNode } from "react";

interface BadgeProps {
  children: ReactNode;
  variant?: "default" | "brand" | "success" | "warning" | "error";
  className?: string;
}

const variants: Record<string, string> = {
  default:
    "bg-[var(--bg-tertiary)] text-[var(--text-secondary)]",
  brand:
    "bg-[var(--brand-glow)] text-[var(--brand-primary)]",
  success:
    "bg-[rgba(34,197,94,0.15)] text-[var(--success)]",
  warning:
    "bg-[rgba(245,158,11,0.15)] text-[var(--warning)]",
  error:
    "bg-[rgba(239,68,68,0.15)] text-[var(--error)]",
};

export function Badge({ children, variant = "default", className }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium",
        variants[variant],
        className,
      )}
    >
      {children}
    </span>
  );
}
