/**
 * Home — The Holy Shit Moment.
 *
 * OmniBrain's manifesto says: "Within 30 seconds of opening the app for
 * the first time, the user must have a moment of 'Holy shit, it knows me'."
 *
 * This page delivers that through:
 * 1. Live Activity Pulse — real-time status of what OmniBrain is doing
 * 2. What It Learned — behavioral patterns and insights
 * 3. Quick Action Bar — 3 contextual fast actions
 * 4. Contextual priorities from the briefing (real data, not generic)
 * 5. Next meeting countdown with context
 * 6. Email urgency signals with names
 * 7. Pending proposals with approve/reject
 * 8. Behavioral observations from the pattern engine
 * 9. Smart empty states when data is missing
 */

"use client";

import { useEffect, useRef, useState } from "react";
import {
  Zap,
  Clock,
  Mail,
  Calendar,
  TrendingUp,
  Check,
  X,
  Timer,
  MessageCircle,
  Puzzle,
  Users,
  ClipboardCheck,
  ArrowRight,
  AlertCircle,
  Brain,
  Activity,
  Sparkles,
  ExternalLink,
} from "lucide-react";
import { useStore } from "@/lib/store";
import { useNavigate } from "@/hooks/useNavigate";
import { api, ApiError, type BriefingData, type Proposal, type BrainStatus } from "@/lib/api";
import { Card, CardHeader, CardTitle, CardBody, CardFooter } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { SkeletonCard } from "@/components/ui/skeleton";
import { ApiErrorRecovery } from "@/components/ui/api-error-recovery";
import { cn } from "@/lib/utils";

// ═══════════════════════════════════════════════════════════════════════════
// Helpers
// ═══════════════════════════════════════════════════════════════════════════

function greeting(): string {
  const h = new Date().getHours();
  if (h < 12) return "Good morning";
  if (h < 18) return "Good afternoon";
  return "Good evening";
}

function todayFormatted(): string {
  return new Date().toLocaleDateString("en-US", {
    weekday: "long", month: "long", day: "numeric", year: "numeric",
  });
}

function sourceIcon(source: string) {
  if (source.includes("email") || source.includes("gmail")) return <Mail className="h-4 w-4" />;
  if (source.includes("calendar")) return <Calendar className="h-4 w-4" />;
  if (source.includes("contact")) return <Users className="h-4 w-4" />;
  return <TrendingUp className="h-4 w-4" />;
}

function sourceColor(source: string): string {
  if (source.includes("email")) return "text-[var(--accent-blue)]";
  if (source.includes("calendar")) return "text-[var(--brand-primary)]";
  return "text-[var(--accent-orange)]";
}

function formatUptime(seconds: number): string {
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)}h ${Math.round((seconds % 3600) / 60)}m`;
  return `${Math.round(seconds / 86400)}d`;
}

// ═══════════════════════════════════════════════════════════════════════════
// Live Activity Pulse
// ═══════════════════════════════════════════════════════════════════════════

function LiveActivityPulse({ brainStatus }: { brainStatus: BrainStatus | null }) {
  if (!brainStatus) return null;

  const { uptime_seconds, emails_analyzed, contacts_mapped, patterns_detected, llm_provider, month_cost_usd } = brainStatus;

  return (
    <div className="flex items-center gap-3 px-4 py-3 rounded-[var(--radius-md)] bg-[var(--bg-secondary)] border border-[var(--border-subtle)]">
      {/* Pulse dot */}
      <div className="relative shrink-0">
        <div className="w-2 h-2 rounded-full bg-[var(--success)]" />
        <div className="absolute inset-0 w-2 h-2 rounded-full bg-[var(--success)] animate-ping opacity-60" />
      </div>

      <div className="flex-1 min-w-0 text-xs text-[var(--text-secondary)]">
        <span className="font-medium text-[var(--text-primary)]">Brain active</span>
        {uptime_seconds > 0 && (
          <span className="ml-1.5 text-[var(--text-tertiary)]">
            for {formatUptime(uptime_seconds)}
          </span>
        )}
        <span className="mx-2 text-[var(--border-subtle)]">·</span>
        <span>{emails_analyzed.toLocaleString()} events</span>
        <span className="mx-2 text-[var(--border-subtle)]">·</span>
        <span>{contacts_mapped} contacts</span>
        {patterns_detected > 0 && (
          <>
            <span className="mx-2 text-[var(--border-subtle)]">·</span>
            <span>{patterns_detected} patterns</span>
          </>
        )}
      </div>

      <div className="shrink-0 flex items-center gap-2 text-xs text-[var(--text-tertiary)]">
        <span className="capitalize">{llm_provider}</span>
        {month_cost_usd > 0 && (
          <span className="font-mono">${month_cost_usd.toFixed(3)}/mo</span>
        )}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// Learning Insights Card — "Cosa Ho Imparato Oggi"
// ═══════════════════════════════════════════════════════════════════════════

function LearningInsights({ brainStatus }: { brainStatus: BrainStatus | null }) {
  const navigate = useNavigate();
  if (!brainStatus) return null;

  const { recent_insights, learning_progress, google_connected, emails_analyzed } = brainStatus;

  // Nothing to show if no insights and fully learning
  if (recent_insights.length === 0 && emails_analyzed === 0) {
    return (
      <Card>
        <CardBody className="py-5">
          <div className="flex items-start gap-3">
            <Brain className="h-5 w-5 text-[var(--brand-primary)] shrink-0 mt-0.5" />
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-[var(--text-primary)] mb-1">
                Still learning about you…
              </p>
              {!google_connected ? (
                <p className="text-sm text-[var(--text-secondary)]">
                  Connect Google to let OmniBrain analyze your emails and calendar.
                </p>
              ) : (
                <div>
                  <p className="text-sm text-[var(--text-secondary)] mb-2">
                    Analyzing your data. More you interact, the smarter I get.
                  </p>
                  <div className="h-1.5 bg-[var(--bg-tertiary)] rounded-full overflow-hidden">
                    <div
                      className="h-full bg-[var(--brand-primary)] rounded-full transition-all duration-1000"
                      style={{ width: `${Math.max(5, learning_progress * 100)}%` }}
                    />
                  </div>
                  <p className="text-xs text-[var(--text-tertiary)] mt-1.5">
                    {Math.round(learning_progress * 100)}% of target dataset analyzed
                  </p>
                </div>
              )}
            </div>
          </div>
        </CardBody>
      </Card>
    );
  }

  if (recent_insights.length === 0) return null;

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-[var(--brand-primary)]" />
          <CardTitle>What I Learned</CardTitle>
        </div>
      </CardHeader>
      <CardBody className="space-y-2.5">
        {recent_insights.slice(0, 3).map((insight, i) => (
          <div key={i} className="flex items-start gap-2.5">
            <div className="shrink-0 w-1.5 h-1.5 rounded-full bg-[var(--brand-primary)] mt-2" />
            <p className="text-sm text-[var(--text-secondary)] leading-relaxed">{insight}</p>
          </div>
        ))}
      </CardBody>
      <CardFooter>
        <button
          onClick={() => navigate("knowledge")}
          className="flex items-center gap-1.5 text-xs text-[var(--brand-primary)] hover:opacity-80 transition-opacity"
        >
          <ExternalLink className="h-3 w-3" /> Explore the full knowledge graph
        </button>
      </CardFooter>
    </Card>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// Quick Actions Bar
// ═══════════════════════════════════════════════════════════════════════════

function QuickActionsBar({
  brainStatus,
  briefingData,
  onChat,
}: {
  brainStatus: BrainStatus | null;
  briefingData: BriefingData | null;
  onChat: (text: string) => void;
}) {
  const navigate = useNavigate();
  const hasBriefingToday = briefingData && briefingData.date === new Date().toISOString().slice(0, 10);

  const actions: { label: string; icon: React.ReactNode; action: () => void }[] = [];

  if (!hasBriefingToday) {
    actions.push({
      label: "Generate briefing",
      icon: <Zap className="h-3.5 w-3.5" />,
      action: () => navigate("briefing"),
    });
  }

  actions.push({
    label: "What's urgent?",
    icon: <AlertCircle className="h-3.5 w-3.5" />,
    action: () => onChat("What's most urgent right now? What needs my immediate attention?"),
  });

  actions.push({
    label: "Explore my graph",
    icon: <Brain className="h-3.5 w-3.5" />,
    action: () => navigate("knowledge"),
  });

  if (brainStatus && !brainStatus.google_connected) {
    actions.push({
      label: "Connect Google",
      icon: <ExternalLink className="h-3.5 w-3.5" />,
      action: () => navigate("settings"),
    });
  }

  return (
    <div className="flex flex-wrap gap-2">
      {actions.slice(0, 4).map((action, i) => (
        <button
          key={i}
          onClick={action.action}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-full border border-[var(--border-subtle)] bg-[var(--bg-secondary)] text-xs text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:border-[var(--border-default)] transition-all"
        >
          {action.icon}
          {action.label}
        </button>
      ))}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// Priority Insight Card — the "Holy Shit Moment" element
// ═══════════════════════════════════════════════════════════════════════════

interface PriorityItem {
  rank: number;
  title: string;
  reason: string;
  source: string;
}

function PriorityCard({ item, index, onChat }: {
  item: PriorityItem;
  index: number;
  onChat: (context: string) => void;
}) {
  const isTop = item.rank === 1;

  return (
    <div
      className="animate-spring-in"
      style={{ animationDelay: `${index * 60}ms`, animationFillMode: "both" }}
    >
      <Card variant={isTop ? "urgent" : "default"} className="!animate-none">
        <CardBody>
          <div className="flex items-start gap-3">
            <div className={cn(
              "shrink-0 w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold",
              isTop
                ? "bg-[var(--brand-primary)] text-white"
                : "bg-[var(--bg-tertiary)] text-[var(--text-secondary)]",
            )}>
              {item.rank}
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-0.5">
                <span className={sourceColor(item.source)}>
                  {sourceIcon(item.source)}
                </span>
                <span className="font-semibold text-sm text-[var(--text-primary)]">
                  {item.title}
                </span>
              </div>
              <p className="text-sm text-[var(--text-secondary)] mt-1 leading-relaxed">
                {item.reason}
              </p>
            </div>
          </div>
        </CardBody>
        <CardFooter>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => onChat(`Help me with: ${item.title}. Context: ${item.reason}`)}
          >
            <MessageCircle className="h-3.5 w-3.5" />
            Ask OmniBrain
          </Button>
          <Badge variant={isTop ? "warning" : "default"} className="ml-auto capitalize">
            {item.source.replace(/_/g, " ")}
          </Badge>
        </CardFooter>
      </Card>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// Next Meeting Banner
// ═══════════════════════════════════════════════════════════════════════════

function NextMeetingBanner({ data }: { data: BriefingData }) {
  const { next_meeting, next_meeting_time } = data.calendar;
  if (!next_meeting || next_meeting === "None") return null;

  // Parse countdown
  const now = new Date();
  const meetingTime = next_meeting_time ? new Date(next_meeting_time) : null;
  const minutesUntil = meetingTime
    ? Math.round((meetingTime.getTime() - now.getTime()) / 60000)
    : null;

  const isImminent = minutesUntil !== null && minutesUntil <= 30 && minutesUntil > 0;
  const isPast = minutesUntil !== null && minutesUntil < 0;

  if (isPast || minutesUntil === null || minutesUntil > 480) return null;

  return (
    <div
      className={cn(
        "flex items-center gap-3 px-4 py-3 rounded-[var(--radius-md)] text-sm",
        isImminent
          ? "bg-[color-mix(in_srgb,var(--warning)_10%,transparent)] border border-[var(--warning)]/30"
          : "bg-[var(--bg-secondary)] border border-[var(--border-subtle)]",
      )}
    >
      <Clock className={cn("h-4 w-4 shrink-0", isImminent ? "text-[var(--warning)]" : "text-[var(--brand-primary)]")} />
      <div className="flex-1 min-w-0">
        <span className="font-medium text-[var(--text-primary)] truncate block">{next_meeting}</span>
        <span className="text-[var(--text-tertiary)] text-xs">
          {minutesUntil === 0
            ? "Starting now"
            : `in ${minutesUntil < 60 ? `${minutesUntil}m` : `${Math.round(minutesUntil / 60)}h`}`}
        </span>
      </div>
      {isImminent && (
        <Badge variant="warning" className="shrink-0">Now</Badge>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// Observation Chips — behavioral pattern highlights
// ═══════════════════════════════════════════════════════════════════════════

function ObservationChips({ observations }: { observations: string[] }) {
  if (!observations.length) return null;

  return (
    <div>
      <h3 className="text-xs font-medium text-[var(--text-tertiary)] uppercase tracking-wide mb-2">
        Pattern Detected
      </h3>
      <div className="flex flex-wrap gap-2">
        {observations.slice(0, 3).map((obs, i) => (
          <div
            key={i}
            className="px-3 py-1.5 rounded-full bg-[var(--bg-secondary)] border border-[var(--border-subtle)] text-xs text-[var(--text-secondary)]"
          >
            {obs}
          </div>
        ))}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// Proposal Card (action-required)
// ═══════════════════════════════════════════════════════════════════════════

function ProposalCard({ proposal, index }: { proposal: Proposal; index: number }) {
  const removeProposal = useStore((s) => s.removeProposal);
  const [acting, setActing] = useState(false);
  const [exiting, setExiting] = useState(false);
  const hasAnimated = useRef(false);
  useEffect(() => { hasAnimated.current = true; }, []);

  const icon = proposal.type.includes("email") ? (
    <Mail className="h-4 w-4" />
  ) : proposal.type.includes("calendar") ? (
    <Calendar className="h-4 w-4" />
  ) : (
    <TrendingUp className="h-4 w-4" />
  );

  const exitThenRemove = (id: number) => {
    setExiting(true);
    setTimeout(() => removeProposal(id), 200);
  };

  const [approved, setApproved] = useState(false);
  const [rejected, setRejected] = useState(false);

  const handleApprove = async () => {
    setActing(true);
    try {
      await api.approveProposal(proposal.id);
      setApproved(true);
      setTimeout(() => exitThenRemove(proposal.id), 600);
    } catch { setActing(false); }
  };

  const handleReject = async () => {
    setActing(true);
    try {
      await api.rejectProposal(proposal.id);
      setRejected(true);
      setTimeout(() => exitThenRemove(proposal.id), 400);
    } catch { setActing(false); }
  };

  const handleSnooze = async (hours = 4) => {
    setActing(true);
    try {
      await api.snoozeProposal(proposal.id, hours);
      exitThenRemove(proposal.id);
    } catch { setActing(false); }
  };

  return (
    <div
      className={exiting ? "animate-slide-out-up" : (hasAnimated.current ? undefined : "animate-spring-in")}
      style={exiting ? { animationFillMode: "both" } : (hasAnimated.current ? undefined : { animationDelay: `${index * 50}ms`, animationFillMode: "both" })}
    >
      <Card variant={proposal.priority >= 3 ? "urgent" : "default"} className="!animate-none">
        <CardHeader>
          <div className="flex items-center gap-2">
            <span className="text-[var(--accent-orange)]">{icon}</span>
            <CardTitle>{proposal.title}</CardTitle>
          </div>
          <Badge variant={proposal.priority >= 3 ? "warning" : "default"}>
            {proposal.priority >= 3 ? "Urgent" : "FYI"}
          </Badge>
        </CardHeader>
        <CardBody>{proposal.description}</CardBody>
        <CardFooter>
          <Button
            variant="primary"
            size="sm"
            onClick={handleApprove}
            disabled={acting}
            className={approved ? "!bg-[var(--success)] transition-colors duration-300" : ""}
          >
            {approved ? (
              <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="20 6 9 17 4 12" style={{ strokeDasharray: 24, animation: "draw-check 400ms ease-out forwards" }} />
              </svg>
            ) : <Check className="h-3.5 w-3.5" />}
            {approved ? "Approved" : "Approve"}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={handleReject}
            disabled={acting}
            className={rejected ? "animate-[shake_300ms_ease-in-out] text-[var(--error)]" : ""}
          >
            <X className="h-3.5 w-3.5" /> Dismiss
          </Button>
          <Button variant="ghost" size="sm" onClick={() => handleSnooze(4)} disabled={acting}>
            <Timer className="h-3.5 w-3.5" /> Snooze
          </Button>
          <span className="ml-auto text-xs text-[var(--text-tertiary)]">
            {proposal.created_at
              ? new Date(proposal.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
              : ""}
          </span>
        </CardFooter>
      </Card>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// Stats Row
// ═══════════════════════════════════════════════════════════════════════════

function StatsRow({ stats }: { stats: Record<string, number> }) {
  const mounted = useRef(false);
  useEffect(() => { mounted.current = true; }, []);

  const items = [
    { label: "Events", value: stats.events ?? 0, icon: Calendar },
    { label: "Contacts", value: stats.contacts ?? 0, icon: Users },
    { label: "Proposals", value: stats.proposals_pending ?? 0, icon: ClipboardCheck },
    { label: "Skills", value: stats.installed_skills ?? 0, icon: Puzzle },
  ];

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
      {items.map((item, i) => {
        const Icon = item.icon;
        return (
          <Card key={item.label} className="p-4 !animate-none">
            <div
              className={mounted.current ? undefined : "animate-spring-in"}
              style={mounted.current ? undefined : { animationDelay: `${i * 60}ms`, animationFillMode: "both" }}
            >
              <div className="flex items-center gap-2 mb-1">
                <Icon className="h-4 w-4 text-[var(--text-tertiary)]" />
                <span className="text-xs text-[var(--text-tertiary)]">{item.label}</span>
              </div>
              <span className="text-2xl font-bold text-[var(--text-primary)]">
                {item.value.toLocaleString()}
              </span>
            </div>
          </Card>
        );
      })}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// Main HomePage
// ═══════════════════════════════════════════════════════════════════════════

export function HomePage() {
  const proposals = useStore((s) => s.proposals);
  const setProposals = useStore((s) => s.setProposals);
  const status = useStore((s) => s.status);
  const setStatus = useStore((s) => s.setStatus);
  const briefingData = useStore((s) => s.briefingData);
  const setBriefingData = useStore((s) => s.setBriefingData);
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiError | string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [userName, setUserName] = useState("");
  const [brainStatus, setBrainStatus] = useState<BrainStatus | null>(null);

  useEffect(() => {
    api.getSettings().then((s) => setUserName(s.profile.name)).catch(() => {});
  }, []);

  useEffect(() => {
    // Load brain status in background (non-blocking)
    api.getBrainStatus().then(setBrainStatus).catch(() => {});
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const [statusRes, proposalsRes, briefingRes] = await Promise.allSettled([
          api.getStatus(),
          api.getProposals(),
          api.getBriefingData(),
        ]);
        if (cancelled) return;
        if (statusRes.status === "fulfilled") setStatus(statusRes.value);
        if (proposalsRes.status === "fulfilled") setProposals(proposalsRes.value);
        if (briefingRes.status === "fulfilled") setBriefingData(briefingRes.value);
        if (!cancelled) {
          setLastUpdated(new Date());
          setError(null);
        }
      } catch (err) {
        if (!cancelled) setError(
          err instanceof ApiError ? err : "Couldn't load your data. Check that the backend is running.",
        );
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    return () => { cancelled = true; };
  }, [setStatus, setProposals, setBriefingData]);

  const openChat = (context: string) => {
    useStore.setState({ messages: [] });
    navigate("chat");
    // Small delay so chat page mounts, then inject the context message
    setTimeout(() => {
      useStore.getState().addMessage({
        role: "user",
        content: context,
        timestamp: new Date().toISOString(),
      });
    }, 200);
  };

  // Email urgency signal
  const hasUrgentEmail = briefingData && briefingData.emails.urgent > 0;
  const urgentEmailDesc = hasUrgentEmail
    ? `${briefingData!.emails.urgent} urgent email${briefingData!.emails.urgent > 1 ? "s" : ""} from ${briefingData!.emails.top_senders.slice(0, 2).join(", ") || "your inbox"}`
    : null;

  // Contextual priorities from briefing
  const priorities = briefingData?.priorities ?? [];
  const hasPriorities = priorities.length > 0;

  return (
    <div className="max-w-3xl mx-auto p-6 space-y-8">
      {/* ── Greeting ── */}
      <header className="space-y-1">
        <h1 className="text-[32px] font-bold text-[var(--text-primary)]">
          {briefingData?.greeting || `${greeting()}${userName ? `, ${userName}` : ""}.`}
        </h1>
        <p className="text-sm text-[var(--text-tertiary)]">
          {todayFormatted()}
          {lastUpdated && (
            <span className="ml-2 text-[var(--text-tertiary)]">
              · Updated {lastUpdated.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
            </span>
          )}
        </p>
      </header>

      {/* ── Error ── */}
      {error && (
        <ApiErrorRecovery
          error={error}
          onRetry={() => { setLoading(true); setError(null); window.location.reload(); }}
        />
      )}

      {/* ── Live Activity Pulse ── */}
      {!loading && brainStatus && <LiveActivityPulse brainStatus={brainStatus} />}

      {/* ── Quick Actions Bar ── */}
      {!loading && (
        <QuickActionsBar
          brainStatus={brainStatus}
          briefingData={briefingData}
          onChat={openChat}
        />
      )}

      {/* ── Urgent email signal (if any) ── */}
      {!loading && urgentEmailDesc && (
        <div
          className="flex items-center gap-3 px-4 py-3 rounded-[var(--radius-md)] bg-[color-mix(in_srgb,var(--error)_8%,transparent)] border border-[var(--error)]/20 cursor-pointer"
          onClick={() => openChat(`Check my urgent emails. ${urgentEmailDesc}`)}
        >
          <AlertCircle className="h-4 w-4 text-[var(--error)] shrink-0" />
          <span className="text-sm text-[var(--text-primary)]">{urgentEmailDesc}</span>
          <ArrowRight className="h-4 w-4 text-[var(--text-tertiary)] ml-auto shrink-0" />
        </div>
      )}

      {/* ── Next meeting countdown ── */}
      {!loading && briefingData && <NextMeetingBanner data={briefingData} />}

      {/* ── Holy Shit Moment: Contextual Priorities ── */}
      {!loading && hasPriorities && (
        <section className="space-y-3">
          <h2 className="flex items-center gap-2 text-lg font-semibold text-[var(--text-primary)]">
            <Zap className="h-5 w-5 text-[var(--brand-primary)]" />
            What Matters Today
          </h2>
          <div className="space-y-3">
            {priorities.slice(0, 5).map((item, i) => (
              <PriorityCard key={i} item={item} index={i} onChat={openChat} />
            ))}
          </div>
          {briefingData && briefingData.observations.length > 0 && (
            <ObservationChips observations={briefingData.observations} />
          )}
        </section>
      )}

      {/* ── What I Learned Today ── */}
      {!loading && <LearningInsights brainStatus={brainStatus} />}

      {/* ── Stats ── */}
      {status && <StatsRow stats={status.stats} />}

      {/* ── Proactive Feed (proposals needing approval) ── */}
      <section className="space-y-3">
        <h2 className="flex items-center gap-2 text-lg font-semibold text-[var(--text-primary)]">
          <Zap className="h-5 w-5 text-[var(--accent-orange)]" />
          Needs Your Approval
        </h2>

        {loading ? (
          <div className="space-y-3">
            <SkeletonCard />
            <SkeletonCard />
          </div>
        ) : proposals.length === 0 ? (
          <Card>
            <CardBody className="text-center py-8 space-y-4" role="status">
              <p className="text-[var(--text-tertiary)]">
                {hasPriorities
                  ? "No pending approvals — priorities above need your attention."
                  : "Nothing needs your attention right now. Enjoy the calm. ☀️"}
              </p>
              <div className="flex flex-wrap justify-center gap-2">
                <button
                  onClick={() => navigate("chat")}
                  className="px-4 py-2 rounded-full bg-[var(--bg-tertiary)] text-sm text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors flex items-center gap-1.5"
                >
                  <MessageCircle className="h-3.5 w-3.5" /> Chat with me
                </button>
                <button
                  onClick={() => navigate("briefing")}
                  className="px-4 py-2 rounded-full bg-[var(--bg-tertiary)] text-sm text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors flex items-center gap-1.5"
                >
                  <Zap className="h-3.5 w-3.5" /> Full Briefing
                </button>
              </div>
            </CardBody>
          </Card>
        ) : (
          <div className="space-y-3">
            {proposals.map((p, i) => (
              <ProposalCard key={p.id} proposal={p} index={i} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
