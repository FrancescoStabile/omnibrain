/**
 * Timeline — unified chronological view of all events, proposals, and observations.
 *
 * Filterable by source and date range with infinite scroll pagination.
 * Click any item to expand it for full details + contextual actions.
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
  Loader2,
  ChevronDown,
  ChevronUp,
  Check,
  X,
  MessageCircle,
  MapPin,
  Users,
} from "lucide-react";
import { api, type TimelineItem, type Proposal } from "@/lib/api";
import { Card, CardBody, CardFooter } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useNavigate } from "@/hooks/useNavigate";
import { useStore } from "@/lib/store";
import { cn } from "@/lib/utils";

const PAGE_SIZE = 30;

const sourceFilters = [
  { value: "", label: "All" },
  { value: "gmail", label: "Email" },
  { value: "calendar", label: "Calendar" },
  { value: "proposal", label: "Proposals" },
  { value: "observation", label: "Observations" },
];

function typeIcon(item: TimelineItem) {
  if (item.source === "gmail") return <Mail className="h-4 w-4 text-[var(--accent-blue)]" />;
  if (item.source === "calendar") return <Calendar className="h-4 w-4 text-[var(--brand-primary)]" />;
  if (item.type === "proposal") return <Zap className="h-4 w-4 text-[var(--accent-orange)]" />;
  if (item.type === "observation") return <Eye className="h-4 w-4 text-[var(--brand-primary)]" />;
  return <Clock className="h-4 w-4 text-[var(--text-tertiary)]" />;
}

function sourceBadge(item: TimelineItem) {
  if (item.source === "gmail") return <Badge className="text-[10px] bg-blue-500/10 text-[var(--accent-blue)]">Email</Badge>;
  if (item.source === "calendar") return <Badge className="text-[10px] bg-green-500/10 text-[var(--brand-primary)]">Calendar</Badge>;
  if (item.type === "proposal") return <Badge className="text-[10px] bg-amber-500/10 text-[var(--accent-orange)]">Proposal</Badge>;
  if (item.type === "observation") return <Badge className="text-[10px] bg-purple-500/10 text-purple-400">Observation</Badge>;
  return <Badge className="text-[10px]">{item.source || item.type}</Badge>;
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
    } catch { dateKey = "Unknown"; }
    if (!groups.has(dateKey)) groups.set(dateKey, []);
    groups.get(dateKey)!.push(item);
  }
  return groups;
}

// ── Expandable item detail ──────────────────────────────────────────────────

function ItemDetail({
  item,
  onChat,
}: {
  item: TimelineItem;
  onChat: (text: string) => void;
}) {
  const [approving, setApproving] = useState(false);
  const [rejecting, setRejecting] = useState(false);
  const [done, setDone] = useState<"approved" | "rejected" | null>(null);

  const handleApprove = async () => {
    if (!item.proposal_id) return;
    setApproving(true);
    try {
      await api.approveProposal(item.proposal_id);
      setDone("approved");
    } finally { setApproving(false); }
  };

  const handleReject = async () => {
    if (!item.proposal_id) return;
    setRejecting(true);
    try {
      await api.rejectProposal(item.proposal_id);
      setDone("rejected");
    } finally { setRejecting(false); }
  };

  return (
    <div className="mt-2 pt-2 border-t border-[var(--border-subtle)] space-y-2">
      {/* Email details */}
      {item.source === "gmail" && (
        <>
          {item.sender && (
            <p className="text-xs text-[var(--text-secondary)]">
              <span className="font-medium">From:</span> {item.sender}
            </p>
          )}
          {item.description && (
            <p className="text-xs text-[var(--text-secondary)] leading-relaxed line-clamp-4">
              {item.description}
            </p>
          )}
          <div className="flex flex-wrap gap-2 pt-1">
            <button
              onClick={() => onChat(`Reply to this email from ${item.sender || "the sender"}: "${item.title}". Draft a professional response.`)}
              className="flex items-center gap-1.5 text-xs text-[var(--brand-primary)] hover:opacity-80"
            >
              <MessageCircle className="h-3 w-3" /> Draft reply
            </button>
            <button
              onClick={() => onChat(`Summarize and give me key action items from: "${item.title}" by ${item.sender || "them"}`)}
              className="flex items-center gap-1.5 text-xs text-[var(--text-tertiary)] hover:text-[var(--text-primary)]"
            >
              <Eye className="h-3 w-3" /> Key points
            </button>
          </div>
        </>
      )}

      {/* Calendar details */}
      {item.source === "calendar" && (
        <>
          {item.location && (
            <p className="text-xs text-[var(--text-secondary)] flex items-center gap-1.5">
              <MapPin className="h-3 w-3 text-[var(--text-tertiary)]" /> {item.location}
            </p>
          )}
          {item.attendees && item.attendees.length > 0 && (
            <p className="text-xs text-[var(--text-secondary)] flex items-center gap-1.5">
              <Users className="h-3 w-3 text-[var(--text-tertiary)]" />
              {item.attendees.slice(0, 3).join(", ")}
              {item.attendees.length > 3 && ` +${item.attendees.length - 3} more`}
            </p>
          )}
          {item.description && (
            <p className="text-xs text-[var(--text-secondary)] leading-relaxed line-clamp-3">
              {item.description}
            </p>
          )}
          <button
            onClick={() => onChat(`Prepare me for the meeting "${item.title}". What should I know? What are the key discussion points?`)}
            className="flex items-center gap-1.5 text-xs text-[var(--brand-primary)] hover:opacity-80 pt-1"
          >
            <Zap className="h-3 w-3" /> Prepare brief
          </button>
        </>
      )}

      {/* Proposal inline approve/reject */}
      {item.type === "proposal" && item.proposal_id && !done && (
        <div className="flex items-center gap-2 pt-1">
          <button
            onClick={handleApprove}
            disabled={approving || rejecting}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-[var(--brand-primary)] text-white text-xs font-medium disabled:opacity-50 hover:opacity-90 transition-opacity"
          >
            <Check className="h-3 w-3" /> {approving ? "…" : "Approve"}
          </button>
          <button
            onClick={handleReject}
            disabled={approving || rejecting}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-[var(--bg-tertiary)] text-[var(--text-secondary)] text-xs hover:text-[var(--text-primary)] transition-colors"
          >
            <X className="h-3 w-3" /> Dismiss
          </button>
        </div>
      )}
      {done && (
        <p className="text-xs text-[var(--text-tertiary)]">
          {done === "approved" ? "✓ Approved" : "✕ Dismissed"}
        </p>
      )}

      {/* Observation context */}
      {item.type === "observation" && item.description && (
        <p className="text-xs text-[var(--text-secondary)] leading-relaxed">{item.description}</p>
      )}
    </div>
  );
}

// ── Timeline item card ──────────────────────────────────────────────────────

function TimelineCard({
  item,
  expanded,
  onToggle,
  onChat,
}: {
  item: TimelineItem;
  expanded: boolean;
  onToggle: () => void;
  onChat: (text: string) => void;
}) {
  const hasDetail =
    item.source === "gmail" ||
    item.source === "calendar" ||
    item.type === "proposal" ||
    (item.type === "observation" && !!item.description);

  return (
    <Card
      className={cn(
        "transition-all",
        expanded ? "border-[var(--brand-primary)]/30" : "hover:border-[var(--border-default)]",
        hasDetail ? "cursor-pointer" : "",
      )}
      onClick={hasDetail ? onToggle : undefined}
    >
      <CardBody className="p-3">
        <div className="flex items-start gap-3">
          <div className="mt-0.5 shrink-0">{typeIcon(item)}</div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-sm font-medium text-[var(--text-primary)] truncate">
                {item.title || "Untitled"}
              </span>
              {sourceBadge(item)}
            </div>
            <span className="text-xs text-[var(--text-tertiary)]">
              {formatTimestamp(item.timestamp)}
            </span>

            {expanded && hasDetail && (
              <ItemDetail item={item} onChat={onChat} />
            )}
          </div>
          {hasDetail && (
            <div className="shrink-0 mt-0.5 text-[var(--text-tertiary)]">
              {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            </div>
          )}
        </div>
      </CardBody>
    </Card>
  );
}

// ── Main TimelinePage ──────────────────────────────────────────────────────

export function TimelinePage() {
  const [items, setItems] = useState<TimelineItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [source, setSource] = useState("");
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const sentinelRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();

  const openChat = useCallback((context: string) => {
    useStore.setState({ messages: [] });
    navigate("chat");
    setTimeout(() => {
      useStore.getState().addMessage({
        role: "user",
        content: context,
        timestamp: new Date().toISOString(),
      });
    }, 200);
  }, [navigate]);

  const fetchItems = useCallback(
    async (reset = false) => {
      const currentOffset = reset ? 0 : offset;
      if (reset) setLoading(true);
      else setLoadingMore(true);
      setError(null);
      try {
        const res = await api.getTimeline({ source, limit: PAGE_SIZE, offset: currentOffset });
        if (reset) setItems(res.items);
        else setItems((prev) => [...prev, ...res.items]);
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
    setExpandedId(null);
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
    <div className="max-w-3xl mx-auto p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-[var(--text-primary)]">Timeline</h1>
        <span className="text-sm text-[var(--text-tertiary)]">{total} events</span>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-2">
        <Filter className="h-4 w-4 text-[var(--text-tertiary)] mt-2 shrink-0" />
        {sourceFilters.map((f) => (
          <button
            key={f.value}
            onClick={() => setSource(f.value)}
            className={cn(
              "px-3 py-1.5 rounded-full text-xs font-medium transition-all",
              source === f.value
                ? "bg-[var(--brand-primary)] text-white"
                : "bg-[var(--bg-secondary)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]",
            )}
          >
            {f.label}
          </button>
        ))}
      </div>

      {/* Loading skeleton */}
      {loading && (
        <div className="space-y-3">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="h-14 rounded-[var(--radius-lg)] bg-[var(--bg-secondary)] animate-pulse" />
          ))}
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="p-4 rounded-[var(--radius-md)] bg-[color-mix(in_srgb,var(--error)_8%,transparent)] text-sm text-[var(--error)] flex items-center gap-2">
          {error}
          <button onClick={() => fetchItems(true)} className="ml-auto underline">Retry</button>
        </div>
      )}

      {/* Timeline */}
      {!loading && !error && (
        <div className="relative">
          {/* Vertical line */}
          <div className="absolute left-[19px] top-0 bottom-0 w-px bg-[var(--border-subtle)]" />

          {Array.from(groups.entries()).map(([dateLabel, groupItems]) => (
            <div key={dateLabel} className="mb-6">
              <div className="relative mb-3 flex items-center gap-3">
                <div className="z-10 h-3 w-3 rounded-full bg-[var(--brand-primary)] shrink-0" />
                <h3 className="text-xs font-semibold text-[var(--text-tertiary)] uppercase tracking-wide">
                  {dateLabel}
                </h3>
              </div>

              <div className="ml-8 space-y-2">
                {groupItems.map((item) => (
                  <TimelineCard
                    key={item.id}
                    item={item}
                    expanded={expandedId === item.id}
                    onToggle={() => setExpandedId(expandedId === item.id ? null : item.id)}
                    onChat={openChat}
                  />
                ))}
              </div>
            </div>
          ))}

          {/* Empty state */}
          {items.length === 0 && (
            <div className="py-12 text-center space-y-2">
              <Clock className="mx-auto h-10 w-10 text-[var(--text-tertiary)] opacity-40" />
              <p className="text-sm font-medium text-[var(--text-secondary)]">No events yet</p>
              <p className="text-xs text-[var(--text-tertiary)]">
                Your timeline will populate as OmniBrain observes your activity.
              </p>
            </div>
          )}
        </div>
      )}

      {/* Infinite scroll sentinel */}
      <div ref={sentinelRef} className="h-8 flex items-center justify-center">
        {loadingMore && <Loader2 className="h-5 w-5 animate-spin text-[var(--text-tertiary)]" />}
        {!loadingMore && items.length >= total && items.length > 0 && (
          <span className="text-xs text-[var(--text-tertiary)]">End of timeline</span>
        )}
      </div>
    </div>
  );
}
