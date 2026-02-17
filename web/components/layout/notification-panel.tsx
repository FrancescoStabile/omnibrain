/**
 * NotificationPanel — dropdown showing real-time WebSocket notifications.
 * 
 * Shows notification history with level badges, dismiss buttons,
 * and a clear-all action. Bridges Zustand notifications → visible UI.
 */

"use client";

import { useRef, useEffect } from "react";
import { Bell, X, AlertTriangle, Info, AlertCircle, VolumeX } from "lucide-react";
import { useStore, type ProactiveNotification } from "@/lib/store";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";

const levelConfig: Record<string, { icon: typeof Bell; variant: "default" | "brand" | "success" | "warning" | "error"; label: string }> = {
  critical: { icon: AlertCircle, variant: "error", label: "Critical" },
  important: { icon: AlertTriangle, variant: "warning", label: "Important" },
  fyi: { icon: Info, variant: "brand", label: "FYI" },
  silent: { icon: VolumeX, variant: "default", label: "Silent" },
};

function NotificationItem({
  notification,
  onDismiss,
}: {
  notification: ProactiveNotification;
  onDismiss: (id: string) => void;
}) {
  const config = levelConfig[notification.level] || levelConfig.fyi;
  const Icon = config.icon;
  const time = notification.timestamp
    ? new Date(notification.timestamp).toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
      })
    : "";

  return (
    <div className="flex items-start gap-3 px-4 py-3 hover:bg-[var(--bg-tertiary)] transition-colors group">
      <Icon className="h-4 w-4 mt-0.5 shrink-0 text-[var(--text-tertiary)]" />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-0.5">
          <Badge variant={config.variant} className="text-[10px] px-1.5 py-0">
            {config.label}
          </Badge>
          {notification.title && (
            <span className="text-xs font-medium text-[var(--text-primary)] truncate">
              {notification.title}
            </span>
          )}
        </div>
        <p className="text-sm text-[var(--text-secondary)] line-clamp-2">
          {notification.message}
        </p>
        {time && (
          <span className="text-[10px] text-[var(--text-tertiary)] mt-0.5 block">
            {time}
          </span>
        )}
      </div>
      <button
        onClick={() => onDismiss(notification.id)}
        className="opacity-0 group-hover:opacity-100 shrink-0 text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] transition-all"
        aria-label="Dismiss"
      >
        <X className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}

export function NotificationPanel({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const notifications = useStore((s) => s.notifications);
  const dismissNotification = useStore((s) => s.dismissNotification);
  const panelRef = useRef<HTMLDivElement>(null);

  // Close on click outside
  useEffect(() => {
    if (!open) return;
    const handleClick = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        onClose();
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open, onClose]);

  // Close on Escape
  useEffect(() => {
    if (!open) return;
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [open, onClose]);

  if (!open) return null;

  const clearAll = () => {
    notifications.forEach((n) => dismissNotification(n.id));
  };

  return (
    <div
      ref={panelRef}
      className={cn(
        "absolute right-0 top-full mt-2 w-[380px] max-h-[480px]",
        "rounded-[var(--radius-lg)] border border-[var(--border-default)]",
        "bg-[var(--bg-elevated)] shadow-[var(--shadow-lg)]",
        "flex flex-col overflow-hidden",
        "animate-[slide-up_200ms_ease-out]",
        "z-50",
      )}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--border-subtle)]">
        <span className="text-sm font-semibold text-[var(--text-primary)]">
          Notifications
        </span>
        {notifications.length > 0 && (
          <button
            onClick={clearAll}
            className="text-xs text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] transition-colors"
          >
            Clear all
          </button>
        )}
      </div>

      {/* List */}
      <div className="flex-1 overflow-y-auto divide-y divide-[var(--border-subtle)]">
        {notifications.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 px-4">
            <Bell className="h-8 w-8 text-[var(--text-tertiary)] mb-3" />
            <p className="text-sm text-[var(--text-tertiary)] text-center">
              No notifications yet. OmniBrain will alert you when something needs
              your attention.
            </p>
          </div>
        ) : (
          notifications.map((n) => (
            <NotificationItem
              key={n.id}
              notification={n}
              onDismiss={dismissNotification}
            />
          ))
        )}
      </div>
    </div>
  );
}
