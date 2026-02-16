/**
 * Button — all variants from the UX Bible.
 *
 * primary (gradient CTA), secondary, ghost, danger, icon
 */

import { cn } from "@/lib/utils";
import type { ButtonHTMLAttributes, ReactNode } from "react";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "ghost" | "danger" | "icon";
  size?: "sm" | "md" | "lg";
  children: ReactNode;
}

const base =
  "inline-flex items-center justify-center font-medium transition-all duration-100 active:scale-[0.97] disabled:opacity-50 disabled:pointer-events-none focus-visible:outline-2 focus-visible:outline-[var(--brand-primary)] focus-visible:outline-offset-2";

const variants: Record<string, string> = {
  primary:
    "bg-[var(--gradient-brand)] bg-gradient-to-r from-[#7C3AED] to-[#2563EB] text-white hover:shadow-[var(--shadow-glow)] rounded-[var(--radius-sm)]",
  secondary:
    "bg-[var(--bg-tertiary)] text-[var(--text-primary)] border border-[var(--border-default)] hover:bg-[var(--bg-elevated)] rounded-[var(--radius-sm)]",
  ghost:
    "bg-transparent text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)] rounded-[var(--radius-sm)]",
  danger:
    "bg-[var(--error)] text-white hover:brightness-110 rounded-[var(--radius-sm)]",
  icon: "bg-[var(--bg-tertiary)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] rounded-full",
};

const sizes: Record<string, string> = {
  sm: "h-8 px-3 text-[13px] gap-1.5",
  md: "h-9 px-4 text-sm gap-2",
  lg: "h-11 px-6 text-base gap-2",
};

const iconSizes: Record<string, string> = {
  sm: "h-8 w-8",
  md: "h-9 w-9",
  lg: "h-11 w-11",
};

export function Button({
  variant = "secondary",
  size = "md",
  className,
  children,
  ...props
}: ButtonProps) {
  const sizeClass = variant === "icon" ? iconSizes[size] : sizes[size];

  return (
    <button
      className={cn(base, variants[variant], sizeClass, className)}
      {...props}
    >
      {children}
    </button>
  );
}
