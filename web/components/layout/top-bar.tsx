/**
 * TopBar — header with mobile menu button, theme toggle, and user menu.
 */

"use client";

import { Moon, Sun, User } from "lucide-react";
import { useStore } from "@/lib/store";
import { Button } from "@/components/ui/button";
import { MobileMenuButton } from "./sidebar";

export function TopBar() {
  const { theme, toggleTheme } = useStore();

  return (
    <header className="flex items-center justify-between gap-2 h-14 px-4 sm:px-6 border-b border-[var(--border-subtle)] bg-[var(--bg-primary)]">
      <MobileMenuButton />
      <div className="flex-1" />
      <div className="flex items-center gap-2">
        <Button variant="icon" size="sm" onClick={toggleTheme} aria-label="Toggle theme">
          {theme === "dark" ? (
            <Sun className="h-4 w-4" />
          ) : (
            <Moon className="h-4 w-4" />
          )}
        </Button>
        <Button variant="icon" size="sm" aria-label="User menu">
          <User className="h-4 w-4" />
        </Button>
      </div>
    </header>
  );
}
