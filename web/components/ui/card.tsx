/**
 * Card — the universal container. Every piece of content lives in a Card.
 *
 * Variants: default, elevated, actionable, urgent, success
 */

import { cn } from "@/lib/utils";
import type { HTMLAttributes, ReactNode } from "react";

interface CardProps {
  children: ReactNode;
  variant?: "default" | "elevated" | "actionable" | "urgent" | "success";
  className?: string;
  onClick?: () => void;
}

const variantStyles: Record<string, string> = {
  default:
    "bg-[var(--bg-secondary)] border border-[var(--border-subtle)]",
  elevated:
    "bg-[var(--bg-elevated)] shadow-[var(--shadow-md)] border border-[var(--border-subtle)]",
  actionable:
    "bg-[var(--bg-secondary)] border border-[var(--border-subtle)] hover:bg-[var(--bg-tertiary)] hover:-translate-y-0.5 hover:shadow-[var(--shadow-md)] cursor-pointer transition-all duration-200",
  urgent:
    "bg-[var(--bg-secondary)] border border-[var(--border-subtle)] border-l-[3px] border-l-[var(--warning)]",
  success:
    "bg-[var(--bg-secondary)] border border-[var(--border-subtle)] border-l-[3px] border-l-[var(--success)]",
};

export function Card({
  children,
  variant = "default",
  className,
  onClick,
}: CardProps) {
  return (
    <div
      className={cn(
        "rounded-[var(--radius-md)] p-5",
        "animate-[slide-up_200ms_ease-out]",
        variantStyles[variant],
        className,
      )}
      onClick={onClick}
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : undefined}
    >
      {children}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// Card subcomponents
// ═══════════════════════════════════════════════════════════════════════════

export function CardHeader({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn("flex items-center justify-between mb-3", className)}
    >
      {children}
    </div>
  );
}

export function CardTitle({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <h3 className={cn("text-[15px] font-semibold text-[var(--text-primary)]", className)}>
      {children}
    </h3>
  );
}

export function CardBody({
  children,
  className,
  ...rest
}: {
  children: ReactNode;
  className?: string;
} & HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn("text-sm text-[var(--text-secondary)] leading-relaxed", className)} {...rest}>
      {children}
    </div>
  );
}

export function CardFooter({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex items-center gap-2 mt-3 pt-3 border-t border-[var(--border-subtle)]",
        className,
      )}
    >
      {children}
    </div>
  );
}
