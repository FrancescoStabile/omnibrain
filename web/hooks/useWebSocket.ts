/**
 * WebSocket hook — real-time feed from ProactiveEngine + EventBus.
 *
 * Connects to /api/v1/feed and dispatches notifications to Zustand store.
 * Also fires toast notifications for important/critical events.
 * Auto-reconnects with exponential backoff.
 */

"use client";

import { useEffect, useRef, useCallback } from "react";
import { useStore } from "@/lib/store";

const WS_PATH = "/api/v1/feed";
const PING_INTERVAL_MS = 25_000;
const RECONNECT_BASE_MS = 1_000;
const RECONNECT_MAX_MS = 30_000;

/** Optional toast function injected from AppShell context */
let _toastFn: ((level: string, message: string) => void) | null = null;

export function setWebSocketToastFn(fn: ((level: string, message: string) => void) | null) {
  _toastFn = fn;
}

export function useWebSocket() {
  const addNotification = useStore((s) => s.addNotification);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttempt = useRef(0);
  const pingTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  const connect = useCallback(() => {
    if (typeof window === "undefined") return;

    // Build ws:// or wss:// URL from current origin
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    const url = `${proto}//${window.location.host}${WS_PATH}`;

    try {
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        reconnectAttempt.current = 0;
        // Start keep-alive pings
        pingTimer.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send("ping");
          }
        }, PING_INTERVAL_MS);
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === "pong") return; // keep-alive response

          if (data.type === "notification") {
            addNotification({
              id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
              level: data.level || "info",
              title: data.title || "OmniBrain",
              message: data.message || "",
              timestamp: data.timestamp || new Date().toISOString(),
            });

            // Fire toast for important+ notifications
            if (_toastFn && (data.level === "important" || data.level === "critical" || data.level === "fyi")) {
              _toastFn(data.level, data.message || data.title || "New notification");
            }

            // Browser notification for critical events
            if (data.level === "critical" && typeof Notification !== "undefined" && Notification.permission === "granted") {
              new Notification(data.title || "OmniBrain", {
                body: data.message || "",
                icon: "/favicon.ico",
              });
            }
          }
        } catch {
          // Ignore malformed messages
        }
      };

      ws.onclose = () => {
        if (pingTimer.current) clearInterval(pingTimer.current);
        // Exponential backoff reconnect
        const delay = Math.min(
          RECONNECT_BASE_MS * 2 ** reconnectAttempt.current,
          RECONNECT_MAX_MS,
        );
        reconnectAttempt.current++;
        setTimeout(connect, delay);
      };

      ws.onerror = () => {
        ws.close();
      };
    } catch {
      // WebSocket not available
    }
  }, [addNotification]);

  useEffect(() => {
    connect();

    return () => {
      if (pingTimer.current) clearInterval(pingTimer.current);
      if (wsRef.current) {
        wsRef.current.onclose = null; // Prevent reconnect on unmount
        wsRef.current.close();
      }
    };
  }, [connect]);
}
