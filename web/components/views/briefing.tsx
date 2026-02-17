/**
 * Briefing — structured daily intelligence view.
 *
 * Fetches `GET /api/v1/briefing/data` and renders card-based sections:
 * greeting, email overview, calendar, proposals, priorities, observations.
 * The "Holy Shit" moment — your day, digested.
 */

"use client";

import { useEffect, useCallback } from "react";
import {
  Mail,
  Calendar,
  Zap,
  ListOrdered,
  Lightbulb,
  Brain,
  AlertTriangle,
  Clock,
  Users,
  RefreshCw,
  ArrowRight,
  Check,
  X,
  Timer,
} from "lucide-react";
import { useStore } from "@/lib/store";
import { useNavigate } from "@/hooks/useNavigate";
import {
  api,
  type BriefingData,
  type CalendarEventItem,
  type PriorityItem,
  type Proposal,
} from "@/lib/api";
import { Card, CardHeader, CardTitle, CardBody, CardFooter } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { SkeletonCard } from "@/components/ui/skeleton";

// ═══════════════════════════════════════════════════════════════════════════
// Section: Email Overview
// ═══════════════════════════════════════════════════════════════════════════

function EmailSection({ data }: { data: BriefingData["emails"] }) {
  if (data.total === 0 && data.unread === 0) return null;

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <Mail className="h-4 w-4 text-[var(--accent-blue)]" />
          <CardTitle>Email</CardTitle>
        </div>
        {data.urgent > 0 && (
          <Badge variant="warning">{data.urgent} urgent</Badge>
        )}
      </CardHeader>
      <CardBody>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          <Stat label="Unread" value={data.unread} highlight={data.unread > 0} />
          <Stat label="Urgent" value={data.urgent} highlight={data.urgent > 0} warn />
          <Stat label="Need Reply" value={data.needs_response} />
          <Stat label="Drafts" value={data.drafts_ready} />
        </div>
        {data.top_senders.length > 0 && (
          <div className="mt-3 pt-3 border-t border-[var(--border-subtle)]">
            <span className="text-xs text-[var(--text-tertiary)]">Top senders: </span>
            <span className="text-xs text-[var(--text-secondary)]">
              {data.top_senders.join(", ")}
            </span>
          </div>
        )}
      </CardBody>
    </Card>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// Section: Calendar
// ═══════════════════════════════════════════════════════════════════════════

function CalendarSection({ data }: { data: BriefingData["calendar"] }) {
  if (data.total_events === 0 && !data.next_meeting) return null;

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <Calendar className="h-4 w-4 text-[var(--brand-primary)]" />
          <CardTitle>Today&apos;s Schedule</CardTitle>
        </div>
        <span className="text-xs text-[var(--text-tertiary)]">
          {data.total_events} event{data.total_events !== 1 ? "s" : ""} &middot;{" "}
          {data.total_hours.toFixed(1)}h
        </span>
      </CardHeader>
      <CardBody className="space-y-3">
        {/* Next meeting callout */}
        {data.next_meeting && (
          <div className="flex items-center gap-2 p-2.5 rounded-[var(--radius-sm)] bg-[var(--brand-glow)]">
            <Clock className="h-4 w-4 text-[var(--brand-primary)]" />
            <div>
              <span className="text-sm font-medium text-[var(--text-primary)]">
                {data.next_meeting}
              </span>
              {data.next_meeting_time && (
                <span className="ml-2 text-xs text-[var(--text-tertiary)]">
                  {data.next_meeting_time}
                </span>
              )}
            </div>
          </div>
        )}

        {/* Event list */}
        {data.events.length > 0 && (
          <ul className="space-y-1.5">
            {data.events.map((ev, i) => (
              <EventRow key={i} event={ev} />
            ))}
          </ul>
        )}

        {/* Conflicts */}
        {data.conflicts.length > 0 && (
          <div className="mt-2 p-2.5 rounded-[var(--radius-sm)] bg-[rgba(245,158,11,0.08)] border border-[rgba(245,158,11,0.2)]">
            <div className="flex items-center gap-1.5 mb-1">
              <AlertTriangle className="h-3.5 w-3.5 text-[var(--warning)]" />
              <span className="text-xs font-medium text-[var(--warning)]">
                Conflicts Detected
              </span>
            </div>
            {data.conflicts.map((c, i) => (
              <p key={i} className="text-xs text-[var(--text-secondary)]">
                {c}
              </p>
            ))}
          </div>
        )}
      </CardBody>
    </Card>
  );
}

function EventRow({ event }: { event: CalendarEventItem }) {
  return (
    <li className="flex items-center gap-3 py-1">
      <span className="text-xs font-mono text-[var(--text-tertiary)] w-14 shrink-0">
        {event.time}
      </span>
      <span className="text-sm text-[var(--text-primary)] flex-1 truncate">
        {event.title}
      </span>
      {event.attendees > 0 && (
        <span className="flex items-center gap-1 text-xs text-[var(--text-tertiary)]">
          <Users className="h-3 w-3" />
          {event.attendees}
        </span>
      )}
      <span className="text-xs text-[var(--text-tertiary)]">
        {event.duration}m
      </span>
    </li>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// Section: Proposals (actions waiting)
// ═══════════════════════════════════════════════════════════════════════════

function ProposalsSection({
  data,
  proposals,
}: {
  data: BriefingData["proposals"];
  proposals: Proposal[];
}) {
  const removeProposal = useStore((s) => s.removeProposal);

  if (data.total_pending === 0) return null;

  const handleApprove = async (id: number) => {
    await api.approveProposal(id);
    removeProposal(id);
  };

  const handleReject = async (id: number) => {
    await api.rejectProposal(id);
    removeProposal(id);
  };

  return (
    <section className="space-y-3" aria-label="Pending proposals">
      <div className="flex items-center gap-2">
        <Zap className="h-5 w-5 text-[var(--accent-orange)]" aria-hidden="true" />
        <h2 className="text-lg font-semibold text-[var(--text-primary)]">
          Needs Your Attention
        </h2>
        <Badge variant="warning">{data.total_pending}</Badge>
      </div>

      {proposals.length > 0 ? (
        proposals.map((p) => (
          <Card
            key={p.id}
            variant={p.priority >= 3 ? "urgent" : "default"}
            className="animate-[slide-up_200ms_ease-out]"
          >
            <CardHeader>
              <div className="flex items-center gap-2">
                <span className="text-[var(--accent-orange)]">
                  <ArrowRight className="h-4 w-4" />
                </span>
                <CardTitle>{p.title}</CardTitle>
              </div>
              <Badge variant={p.priority >= 3 ? "warning" : "default"}>
                {p.type}
              </Badge>
            </CardHeader>
            <CardBody>{p.description}</CardBody>
            <CardFooter>
              <Button
                variant="primary"
                size="sm"
                onClick={() => handleApprove(p.id)}
              >
                <Check className="h-3.5 w-3.5" />
                Approve
              </Button>
              <Button variant="ghost" size="sm" onClick={() => handleReject(p.id)}>
                <X className="h-3.5 w-3.5" />
                Dismiss
              </Button>
              <Button variant="ghost" size="sm">
                <Timer className="h-3.5 w-3.5" />
                Snooze
              </Button>
            </CardFooter>
          </Card>
        ))
      ) : (
        <Card>
          <CardBody>
            <p className="text-sm text-[var(--text-tertiary)]">
              {data.total_pending} pending proposal
              {data.total_pending !== 1 ? "s" : ""} — load proposals view for
              details.
            </p>
          </CardBody>
        </Card>
      )}
    </section>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// Section: Priorities
// ═══════════════════════════════════════════════════════════════════════════

function PrioritiesSection({ items }: { items: PriorityItem[] }) {
  if (items.length === 0) return null;

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <ListOrdered className="h-4 w-4 text-[var(--success)]" />
          <CardTitle>Today&apos;s Priorities</CardTitle>
        </div>
      </CardHeader>
      <CardBody>
        <ol className="space-y-2">
          {items.map((item) => (
            <li key={item.rank} className="flex gap-3">
              <span className="flex items-center justify-center h-6 w-6 rounded-full bg-[var(--bg-tertiary)] text-xs font-bold text-[var(--text-primary)] shrink-0">
                {item.rank}
              </span>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-[var(--text-primary)] truncate">
                  {item.title}
                </p>
                <p className="text-xs text-[var(--text-tertiary)]">{item.reason}</p>
              </div>
              <Badge variant="default">{item.source}</Badge>
            </li>
          ))}
        </ol>
      </CardBody>
    </Card>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// Section: Observations & Memory
// ═══════════════════════════════════════════════════════════════════════════

function InsightsSection({
  observations,
  highlights,
}: {
  observations: string[];
  highlights: string[];
}) {
  if (observations.length === 0 && highlights.length === 0) return null;

  return (
    <div className="grid gap-3 md:grid-cols-2">
      {observations.length > 0 && (
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Lightbulb className="h-4 w-4 text-[var(--accent-orange)]" />
              <CardTitle>Observations</CardTitle>
            </div>
          </CardHeader>
          <CardBody>
            <ul className="space-y-1.5">
              {observations.map((obs, i) => (
                <li key={i} className="flex gap-2 text-sm">
                  <span className="text-[var(--text-tertiary)]">•</span>
                  <span>{obs}</span>
                </li>
              ))}
            </ul>
          </CardBody>
        </Card>
      )}

      {highlights.length > 0 && (
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Brain className="h-4 w-4 text-[var(--brand-primary)]" />
              <CardTitle>Memory Highlights</CardTitle>
            </div>
          </CardHeader>
          <CardBody>
            <ul className="space-y-1.5">
              {highlights.map((h, i) => (
                <li key={i} className="flex gap-2 text-sm">
                  <span className="text-[var(--text-tertiary)]">•</span>
                  <span>{h}</span>
                </li>
              ))}
            </ul>
          </CardBody>
        </Card>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// Stat mini-component
// ═══════════════════════════════════════════════════════════════════════════

function Stat({
  label,
  value,
  highlight,
  warn,
}: {
  label: string;
  value: number;
  highlight?: boolean;
  warn?: boolean;
}) {
  return (
    <div className="text-center">
      <div
        className={`text-2xl font-bold ${
          warn && highlight
            ? "text-[var(--warning)]"
            : highlight
              ? "text-[var(--brand-primary)]"
              : "text-[var(--text-primary)]"
        }`}
      >
        {value}
      </div>
      <div className="text-xs text-[var(--text-tertiary)]">{label}</div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// Empty state
// ═══════════════════════════════════════════════════════════════════════════

function EmptyBriefing() {
  const navigate = useNavigate();

  return (
    <Card className="py-12">
      <CardBody className="text-center space-y-4">
        <Brain className="h-10 w-10 mx-auto text-[var(--brand-primary)] opacity-40" />
        <p className="text-lg font-medium text-[var(--text-primary)]">
          Your briefing is building up
        </p>
        <p className="text-sm text-[var(--text-tertiary)] max-w-sm mx-auto">
          Chat with me about your week, your goals, and your commitments —
          the more I know, the better your morning briefings get.
        </p>
        <button
          onClick={() => navigate("chat")}
          className="mt-2 px-5 py-2 rounded-full bg-[var(--brand-primary)] text-white text-sm font-medium hover:opacity-90 transition-opacity"
        >
          Start chatting
        </button>
      </CardBody>
    </Card>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// Main BriefingPage
// ═══════════════════════════════════════════════════════════════════════════

export function BriefingPage() {
  const {
    briefingData,
    setBriefingData,
    briefingLoading,
    setBriefingLoading,
    proposals,
    setProposals,
  } = useStore();

  const loadBriefing = useCallback(async () => {
    setBriefingLoading(true);
    try {
      const [data, props] = await Promise.allSettled([
        api.getBriefingData(),
        api.getProposals(),
      ]);
      if (data.status === "fulfilled") setBriefingData(data.value);
      if (props.status === "fulfilled") setProposals(props.value);
    } finally {
      setBriefingLoading(false);
    }
  }, [setBriefingData, setBriefingLoading, setProposals]);

  useEffect(() => {
    loadBriefing();
  }, [loadBriefing]);

  const d = briefingData;

  return (
    <div className="max-w-3xl mx-auto p-6 space-y-6" role="region" aria-label="Daily briefing">
      {/* ── Greeting ── */}
      <header className="flex items-end justify-between">
        <div className="space-y-1">
          <h1 className="text-[32px] font-bold text-[var(--text-primary)]">
            {d?.greeting || "Good morning."}
          </h1>
          <p className="text-sm text-[var(--text-tertiary)]">
            {d?.date || new Date().toLocaleDateString("en-US", {
              weekday: "long",
              month: "long",
              day: "numeric",
            })}
          </p>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={loadBriefing}
          disabled={briefingLoading}
          className={briefingLoading ? "animate-spin" : ""}
          aria-label="Refresh briefing"
        >
          <RefreshCw className="h-4 w-4" />
        </Button>
      </header>

      {/* ── Loading ── */}
      {briefingLoading && !d && (
        <div className="space-y-3" role="status" aria-label="Loading briefing">
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
        </div>
      )}

      {/* ── Empty ── */}
      {!briefingLoading && !d && <EmptyBriefing />}

      {/* ── Sections ── */}
      {d && (
        <>
          <EmailSection data={d.emails} />
          <CalendarSection data={d.calendar} />
          <ProposalsSection data={d.proposals} proposals={proposals} />
          <PrioritiesSection items={d.priorities} />
          <InsightsSection
            observations={d.observations}
            highlights={d.memory_highlights}
          />
        </>
      )}
    </div>
  );
}
