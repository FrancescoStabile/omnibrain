/**
 * TopBar — header with mobile menu, notification bell, theme toggle, user menu.
 */

"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { Moon, Sun, User, Bell, LogOut, ChevronDown, WifiOff } from "lucide-react";
import { useStore } from "@/lib/store";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { MobileMenuButton } from "./sidebar";
import { NotificationPanel } from "./notification-panel";
import { cn } from "@/lib/utils";
import { useNavigate } from "@/hooks/useNavigate";
import { useOnlineStatus } from "@/hooks/useOnlineStatus";

export function TopBar() {
  const { theme, toggleTheme, notifications, googleConnected, setGoogleConnected, wsStatus } = useStore();
  const online = useOnlineStatus();
  const navigate = useNavigate();
  const [notifOpen, setNotifOpen] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [userName, setUserName] = useState("");
  const userMenuRef = useRef<HTMLDivElement>(null);
  const unreadCount = notifications.length;

  // Load user name (for display in menu)
  useEffect(() => {
    api.getSettings().then((s) => {
      if (s.profile?.name) setUserName(s.profile.name);
    }).catch(() => {});
  }, []);

  // Close user menu on click outside
  useEffect(() => {
    if (!userMenuOpen) return;
    const handleClick = (e: MouseEvent) => {
      if (userMenuRef.current && !userMenuRef.current.contains(e.target as Node)) {
        setUserMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [userMenuOpen]);

  const handleDisconnectGoogle = useCallback(async () => {
    try {
      await api.disconnectGoogle();
      setGoogleConnected(false);
      setUserMenuOpen(false);
    } catch { /* ignore */ }
  }, [setGoogleConnected]);

  return (
    <>
      {/* Offline banner */}
      {!online && (
        <div className="flex items-center justify-center gap-2 bg-[var(--warning)] px-4 py-1.5 text-xs font-medium text-black">
          <WifiOff className="h-3.5 w-3.5" />
          You&apos;re offline. Reconnect to sync.
        </div>
      )}
    <header className="flex items-center justify-between gap-2 h-14 px-4 sm:px-6 border-b border-[var(--border-subtle)] bg-[var(--bg-primary)]">
      <MobileMenuButton />
      <div className="flex-1" />
      <div className="flex items-center gap-1.5">
        {/* WebSocket status indicator */}
        <div
          title={wsStatus === "connected" ? "Connected" : wsStatus === "reconnecting" ? "Reconnecting..." : "Disconnected"}
          className={cn(
            "h-2 w-2 rounded-full transition-colors",
            wsStatus === "connected" && "bg-[var(--success)]",
            wsStatus === "reconnecting" && "bg-[var(--warning)] animate-pulse",
            wsStatus === "disconnected" && "bg-[var(--error)]",
          )}
        />
        {/* Theme toggle */}
        <Button variant="icon" size="sm" onClick={toggleTheme} aria-label="Toggle theme">
          {theme === "dark" ? (
            <Sun className="h-4 w-4" />
          ) : (
            <Moon className="h-4 w-4" />
          )}
        </Button>

        {/* Notification bell */}
        <div className="relative">
          <Button
            variant="icon"
            size="sm"
            onClick={() => { setNotifOpen(!notifOpen); setUserMenuOpen(false); }}
            aria-label={`Notifications${unreadCount > 0 ? ` (${unreadCount} new)` : ""}`}
          >
            <Bell className="h-4 w-4" />
            {unreadCount > 0 && (
              <span className="absolute -top-0.5 -right-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-[var(--error)] text-[10px] font-bold text-white px-1">
                {unreadCount > 99 ? "99+" : unreadCount}
              </span>
            )}
          </Button>
          <NotificationPanel open={notifOpen} onClose={() => setNotifOpen(false)} />
        </div>

        {/* User menu */}
        <div className="relative" ref={userMenuRef}>
          <button
            onClick={() => { setUserMenuOpen(!userMenuOpen); setNotifOpen(false); }}
            className={cn(
              "flex items-center gap-1.5 px-2 py-1.5 rounded-[var(--radius-sm)]",
              "text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)]",
              "transition-colors text-sm",
            )}
          >
            <div className="h-6 w-6 rounded-full bg-gradient-to-br from-[var(--brand-primary)] to-[#2563EB] flex items-center justify-center">
              <User className="h-3.5 w-3.5 text-white" />
            </div>
            {userName && (
              <span className="hidden sm:inline font-medium max-w-[120px] truncate">
                {userName}
              </span>
            )}
            <ChevronDown className="h-3 w-3 hidden sm:block" />
          </button>

          {userMenuOpen && (
            <div className="absolute right-0 top-full mt-2 w-56 rounded-[var(--radius-lg)] border border-[var(--border-default)] bg-[var(--bg-elevated)] shadow-[var(--shadow-lg)] overflow-hidden animate-[slide-up_200ms_ease-out] z-50">
              {userName && (
                <div className="px-4 py-3 border-b border-[var(--border-subtle)]">
                  <p className="text-sm font-medium text-[var(--text-primary)] truncate">{userName}</p>
                  <p className="text-xs text-[var(--text-tertiary)]">
                    {googleConnected ? "Google connected" : "Local mode"}
                  </p>
                </div>
              )}
              <div className="py-1">
                <button
                  onClick={() => { navigate("settings"); setUserMenuOpen(false); }}
                  className="flex items-center gap-2 w-full px-4 py-2 text-sm text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)] transition-colors"
                >
                  <User className="h-4 w-4" />
                  Settings
                </button>
                {googleConnected && (
                  <button
                    onClick={handleDisconnectGoogle}
                    className="flex items-center gap-2 w-full px-4 py-2 text-sm text-[var(--error)] hover:bg-[var(--bg-tertiary)] transition-colors"
                  >
                    <LogOut className="h-4 w-4" />
                    Disconnect Google
                  </button>
                )}
              </div>
              <div className="px-4 py-2 border-t border-[var(--border-subtle)]">
                <p className="text-[10px] text-[var(--text-tertiary)]">
                  OmniBrain v2.0 &middot; MIT License
                </p>
              </div>
            </div>
          )}
        </div>
      </div>
    </header>
    </>
  );
}
