/**
 * Input — text input with focus animation.
 */

import { cn } from "@/lib/utils";
import { forwardRef, type InputHTMLAttributes } from "react";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ className, ...props }, ref) => (
    <input
      ref={ref}
      className={cn(
        "w-full h-10 px-3 rounded-[var(--radius-sm)]",
        "bg-[var(--bg-secondary)] border border-[var(--border-default)]",
        "text-sm text-[var(--text-primary)] placeholder:text-[var(--text-tertiary)]",
        "transition-colors duration-150",
        "focus:border-[var(--brand-primary)] focus:outline-none focus:ring-1 focus:ring-[var(--brand-primary)]",
        className,
      )}
      {...props}
    />
  ),
);

Input.displayName = "Input";
