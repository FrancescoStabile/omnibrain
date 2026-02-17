/**
 * Home — Briefing + Proactive Feed.
 *
 * The daily view: greeting, overnight summary, pending proposals,
 * today's schedule. The "addiction loop" entry point.
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
} from "lucide-react";
import { useStore } from "@/lib/store";
import { useNavigate } from "@/hooks/useNavigate";
import { api, type Briefing, type BriefingData, type Proposal } from "@/lib/api";
import { Card, CardHeader, CardTitle, CardBody, CardFooter } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { SkeletonCard } from "@/components/ui/skeleton";

// ═══════════════════════════════════════════════════════════════════════════
// Greeting
// ═══════════════════════════════════════════════════════════════════════════

function greeting(): string {
  const h = new Date().getHours();
  if (h < 12) return "Good morning";
  if (h < 18) return "Good afternoon";
  return "Good evening";
}

function todayFormatted(): string {
  return new Date().toLocaleDateString("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
    year: "numeric",
  });
}

// ═══════════════════════════════════════════════════════════════════════════
// Insight Card (proposal)
// ═══════════════════════════════════════════════════════════════════════════

function InsightCard({ proposal, index }: { proposal: Proposal; index: number }) {
  const removeProposal = useStore((s) => s.removeProposal);
  const [acting, setActing] = useState(false);
  const [exiting, setExiting] = useState(false);
  const cardRef = useRef<HTMLDivElement>(null);

  const icon = proposal.type.includes("email") ? (
    <Mail className="h-4 w-4" />
  ) : proposal.type.includes("calendar") ? (
    <Calendar className="h-4 w-4" />
  ) : (
    <TrendingUp className="h-4 w-4" />
  );

  const exitThenRemove = (id: number) => {
    setExiting(true);
    // Wait for exit animation to complete
    setTimeout(() => removeProposal(id), 200);
  };

  const handleApprove = async () => {
    setActing(true);
    try {
      await api.approveProposal(proposal.id);
      exitThenRemove(proposal.id);
    } catch {
      setActing(false);
    }
  };

  const handleReject = async () => {
    setActing(true);
    try {
      await api.rejectProposal(proposal.id);
      exitThenRemove(proposal.id);
    } catch {
      setActing(false);
    }
  };

  const handleSnooze = async (hours = 4) => {
    setActing(true);
    try {
      await api.snoozeProposal(proposal.id, hours);
      exitThenRemove(proposal.id);
    } catch {
      setActing(false);
    }
  };

  return (
    <div
      ref={cardRef}
      className={exiting ? "animate-slide-out-up" : "animate-spring-in"}
      style={{ animationDelay: exiting ? "0ms" : `${index * 50}ms`, animationFillMode: "both" }}
    >
      <Card
        variant={proposal.priority >= 3 ? "urgent" : "default"}
        className="!animate-none"
      >
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
          aria-label={`Approve: ${proposal.title}`}
        >
          <Check className="h-3.5 w-3.5" />
          Approve
        </Button>
        <Button variant="ghost" size="sm" onClick={handleReject} disabled={acting} aria-label={`Dismiss: ${proposal.title}`}>
          <X className="h-3.5 w-3.5" />
          Dismiss
        </Button>
        <Button variant="ghost" size="sm" onClick={() => handleSnooze(4)} disabled={acting} aria-label={`Snooze: ${proposal.title}`}>
          <Timer className="h-3.5 w-3.5" />
          Snooze
        </Button>
        <span className="ml-auto text-xs text-[var(--text-tertiary)]">
          {proposal.created_at
            ? new Date(proposal.created_at).toLocaleTimeString([], {
                hour: "2-digit",
                minute: "2-digit",
              })
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
              className="animate-spring-in"
              style={{ animationDelay: `${i * 60}ms`, animationFillMode: "both" }}
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
  const { proposals, setProposals, status, setStatus, briefingData, setBriefingData } = useStore();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [userName, setUserName] = useState("");

  useEffect(() => {
    api.getSettings().then((s) => setUserName(s.profile.name)).catch(() => {});
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
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [setStatus, setProposals, setBriefingData]);

  return (
    <div className="max-w-3xl mx-auto p-6 space-y-8">
      {/* ── Greeting ── */}
      <header className="space-y-1">
        <h1 className="text-[32px] font-bold text-[var(--text-primary)]">
          {briefingData?.greeting || `${greeting()}${userName ? `, ${userName}` : ""}.`}
        </h1>
        <p className="text-sm text-[var(--text-tertiary)]">{todayFormatted()}</p>
      </header>

      {/* ── Quick Briefing Summary ── */}
      {briefingData && (
        <Card
          variant="actionable"
          onClick={() => navigate("briefing")}
        >
          <CardHeader>
            <div className="flex items-center gap-2">
              <Zap className="h-4 w-4 text-[var(--brand-primary)]" />
              <CardTitle>Today&apos;s Briefing</CardTitle>
            </div>
            <Badge variant="brand">View →</Badge>
          </CardHeader>
          <CardBody>
            <div className="flex flex-wrap gap-x-6 gap-y-1 text-sm">
              {briefingData.emails.unread > 0 && (
                <span>
                  <Mail className="inline h-3.5 w-3.5 mr-1 text-[var(--accent-blue)]" />
                  {briefingData.emails.unread} unread email{briefingData.emails.unread !== 1 ? "s" : ""}
                </span>
              )}
              {briefingData.calendar.total_events > 0 && (
                <span>
                  <Calendar className="inline h-3.5 w-3.5 mr-1 text-[var(--brand-primary)]" />
                  {briefingData.calendar.total_events} event{briefingData.calendar.total_events !== 1 ? "s" : ""}
                </span>
              )}
              {briefingData.proposals.total_pending > 0 && (
                <span>
                  <TrendingUp className="inline h-3.5 w-3.5 mr-1 text-[var(--accent-orange)]" />
                  {briefingData.proposals.total_pending} pending
                </span>
              )}
              {briefingData.memory_highlights.length > 0 && (
                <span className="text-[var(--text-tertiary)]">
                  {briefingData.memory_highlights.length} memory note{briefingData.memory_highlights.length !== 1 ? "s" : ""}
                </span>
              )}
            </div>
          </CardBody>
        </Card>
      )}

      {/* ── Stats ── */}
      {status && <StatsRow stats={status.stats} />}

      {/* ── Proactive Feed ── */}
      <section className="space-y-3">
        <h2 className="flex items-center gap-2 text-lg font-semibold text-[var(--text-primary)]">
          <Zap className="h-5 w-5 text-[var(--accent-orange)]" />
          Needs Your Attention
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
                Nothing needs your attention right now. Enjoy the calm. ☀️
              </p>
              <div className="flex flex-wrap justify-center gap-2">
                <button
                  onClick={() => navigate("chat")}
                  className="px-4 py-2 rounded-full bg-[var(--bg-tertiary)] text-sm text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors flex items-center gap-1.5"
                >
                  <MessageCircle className="h-3.5 w-3.5" /> Chat with me
                </button>
                <button
                  onClick={() => navigate("skills")}
                  className="px-4 py-2 rounded-full bg-[var(--bg-tertiary)] text-sm text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors flex items-center gap-1.5"
                >
                  <Puzzle className="h-3.5 w-3.5" /> Explore Skills
                </button>
              </div>
            </CardBody>
          </Card>
        ) : (
          <div className="space-y-3">
            {proposals.map((p, i) => (
              <InsightCard key={p.id} proposal={p} index={i} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
