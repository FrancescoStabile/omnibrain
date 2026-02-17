/**
 * Timeline — unified chronological view of all events, proposals, and observations.
 *
 * Filterable by source and date range with infinite scroll pagination.
 */

"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import {
  Clock,
  Mail,
  Calendar,
  Zap,
  Eye,
  Filter,
  ChevronDown,
  Loader2,
} from "lucide-react";
import { api, type TimelineItem } from "@/lib/api";
import { Card, CardBody } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";

const PAGE_SIZE = 30;

const sourceFilters = [
  { value: "", label: "All" },
  { value: "gmail", label: "Email" },
  { value: "calendar", label: "Calendar" },
  { value: "proposal", label: "Proposals" },
  { value: "observation", label: "Observations" },
];

function typeIcon(item: TimelineItem) {
  if (item.source === "gmail") return <Mail className="h-4 w-4 text-blue-400" />;
  if (item.source === "calendar") return <Calendar className="h-4 w-4 text-green-400" />;
  if (item.type === "proposal") return <Zap className="h-4 w-4 text-amber-400" />;
  if (item.type === "observation") return <Eye className="h-4 w-4 text-purple-400" />;
  return <Clock className="h-4 w-4 text-muted-foreground" />;
}

function sourceBadge(item: TimelineItem) {
  const colors: Record<string, string> = {
    gmail: "bg-blue-500/20 text-blue-400",
    calendar: "bg-green-500/20 text-green-400",
    proposal: "bg-amber-500/20 text-amber-400",
    observation: "bg-purple-500/20 text-purple-400",
  };
  return (
    <Badge className={colors[item.source] || "bg-muted text-muted-foreground"}>
      {item.source || item.type}
    </Badge>
  );
}

function formatTimestamp(ts: string): string {
  if (!ts) return "";
  try {
    const d = new Date(ts.replace(" ", "T"));
    const now = new Date();
    const diffMs = now.getTime() - d.getTime();
    const diffH = diffMs / 3_600_000;

    if (diffH < 1) return `${Math.round(diffH * 60)}m ago`;
    if (diffH < 24) return `${Math.round(diffH)}h ago`;
    if (diffH < 48) return "Yesterday";
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  } catch {
    return ts;
  }
}

function groupByDate(items: TimelineItem[]): Map<string, TimelineItem[]> {
  const groups = new Map<string, TimelineItem[]>();
  for (const item of items) {
    const ts = item.timestamp?.replace(" ", "T") || "";
    let dateKey: string;
    try {
      const d = new Date(ts);
      const now = new Date();
      if (d.toDateString() === now.toDateString()) dateKey = "Today";
      else if (d.toDateString() === new Date(now.getTime() - 86_400_000).toDateString()) dateKey = "Yesterday";
      else dateKey = d.toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" });
    } catch {
      dateKey = "Unknown";
    }
    if (!groups.has(dateKey)) groups.set(dateKey, []);
    groups.get(dateKey)!.push(item);
  }
  return groups;
}

export function TimelinePage() {
  const [items, setItems] = useState<TimelineItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [source, setSource] = useState("");
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const sentinelRef = useRef<HTMLDivElement>(null);

  const fetchItems = useCallback(
    async (reset = false) => {
      const currentOffset = reset ? 0 : offset;
      if (reset) setLoading(true);
      else setLoadingMore(true);
      setError(null);

      try {
        const res = await api.getTimeline({ source, limit: PAGE_SIZE, offset: currentOffset });
        if (reset) {
          setItems(res.items);
        } else {
          setItems((prev) => [...prev, ...res.items]);
        }
        setTotal(res.total);
        setOffset(currentOffset + res.items.length);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load timeline");
      } finally {
        setLoading(false);
        setLoadingMore(false);
      }
    },
    [source, offset],
  );

  // Initial load + reload on filter change
  useEffect(() => {
    setOffset(0);
    fetchItems(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [source]);

  // Infinite scroll
  useEffect(() => {
    const el = sentinelRef.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && !loadingMore && items.length < total) {
          fetchItems(false);
        }
      },
      { threshold: 0.1 },
    );
    observer.observe(el);
    return () => observer.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items.length, total, loadingMore]);

  const groups = groupByDate(items);

  return (
    <div className="mx-auto max-w-3xl space-y-6 p-4 sm:p-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold tracking-tight">Timeline</h1>
        <span className="text-sm text-muted-foreground">{total} events</span>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-2">
        <Filter className="h-4 w-4 text-muted-foreground mt-2" />
        {sourceFilters.map((f) => (
          <Button
            key={f.value}
            variant={source === f.value ? "primary" : "ghost"}
            size="sm"
            onClick={() => setSource(f.value)}
          >
            {f.label}
          </Button>
        ))}
      </div>

      {/* Loading skeleton */}
      {loading && (
        <div className="space-y-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-16 w-full rounded-xl" />
          ))}
        </div>
      )}

      {/* Error */}
      {error && (
        <Card className="border-destructive/50">
          <CardBody>
            <p className="text-destructive">{error}</p>
            <Button variant="ghost" size="sm" className="mt-2" onClick={() => fetchItems(true)}>
              Try Again
            </Button>
          </CardBody>
        </Card>
      )}

      {/* Timeline */}
      {!loading && !error && (
        <div className="relative">
          {/* Vertical line */}
          <div className="absolute left-[19px] top-0 bottom-0 w-px bg-border" />

          {Array.from(groups.entries()).map(([dateLabel, groupItems]) => (
            <div key={dateLabel} className="mb-6">
              <div className="relative mb-3 flex items-center gap-3">
                <div className="z-10 h-3 w-3 rounded-full bg-primary" />
                <h3 className="text-sm font-semibold text-muted-foreground">{dateLabel}</h3>
              </div>

              <div className="ml-10 space-y-2">
                {groupItems.map((item) => (
                  <Card key={item.id} className="transition-colors hover:bg-accent/50">
                    <CardBody className="flex items-start gap-3 p-3">
                      <div className="mt-0.5">{typeIcon(item)}</div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-medium truncate">{item.title || "Untitled"}</span>
                          {sourceBadge(item)}
                        </div>
                        <span className="text-xs text-muted-foreground">{formatTimestamp(item.timestamp)}</span>
                      </div>
                    </CardBody>
                  </Card>
                ))}
              </div>
            </div>
          ))}

          {/* Empty state */}
          {items.length === 0 && (
            <div className="py-12 text-center text-muted-foreground">
              <Clock className="mx-auto mb-3 h-10 w-10 opacity-50" />
              <p className="text-lg font-medium">No events yet</p>
              <p className="text-sm">Your timeline will populate as OmniBrain observes your activity.</p>
            </div>
          )}
        </div>
      )}

      {/* Infinite scroll sentinel */}
      <div ref={sentinelRef} className="h-8 flex items-center justify-center">
        {loadingMore && <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />}
        {!loadingMore && items.length >= total && items.length > 0 && (
          <span className="text-xs text-muted-foreground">End of timeline</span>
        )}
      </div>
    </div>
  );
}
