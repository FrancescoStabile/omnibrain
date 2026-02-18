/**
 * Transparency — Layer 3 of the OmniBrain manifesto.
 *
 * "Your AI must be transparent. You must be able to see what data left
 * your machine, when, why, and how much it cost."
 *
 * Shows: LLM call log, cost breakdown, daily chart, per-provider stats.
 */

"use client";

import { useState, useEffect, useCallback } from "react";
import { Shield, DollarSign, Zap, Calendar, RefreshCw, ChevronDown, ChevronUp } from "lucide-react";
import { api, type TransparencyCall, type TransparencyStats } from "@/lib/api";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

// ═══════════════════════════════════════════════════════════════════════════
// Stat card
// ═══════════════════════════════════════════════════════════════════════════

function StatCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <Card className="p-4">
      <p className="text-xs text-[var(--text-tertiary)] uppercase tracking-wide mb-1">{label}</p>
      <p className="text-2xl font-bold text-[var(--text-primary)]">{value}</p>
      {sub && <p className="text-xs text-[var(--text-secondary)] mt-0.5">{sub}</p>}
    </Card>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// Call row
// ═══════════════════════════════════════════════════════════════════════════

function CallRow({ call }: { call: TransparencyCall }) {
  const [expanded, setExpanded] = useState(false);
  const ts = new Date(call.timestamp);
  const timeStr = ts.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  const dateStr = ts.toLocaleDateString([], { month: "short", day: "numeric" });

  return (
    <div className="border-b border-[var(--border-subtle)] last:border-0">
      <button
        className="w-full flex items-center gap-3 py-3 px-1 text-left hover:bg-[var(--bg-tertiary)] rounded transition-colors"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="shrink-0 w-14 text-right">
          <p className="text-xs text-[var(--text-tertiary)]">{dateStr}</p>
          <p className="text-xs text-[var(--text-tertiary)]">{timeStr}</p>
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-medium text-[var(--text-primary)] capitalize">
              {call.source || "chat"}
            </span>
            <Badge variant="default" className="text-[10px] capitalize">{call.provider}</Badge>
            {call.had_error && <Badge variant="danger" className="text-[10px]">error</Badge>}
            {call.had_tools && <Badge variant="default" className="text-[10px]">tools</Badge>}
          </div>
          <p className="text-xs text-[var(--text-tertiary)] mt-0.5 truncate">{call.model}</p>
        </div>

        <div className="shrink-0 text-right">
          <p className="text-xs font-mono text-[var(--text-primary)]">
            ${call.cost_usd.toFixed(5)}
          </p>
          <p className="text-xs text-[var(--text-tertiary)]">
            {(call.input_tokens + call.output_tokens).toLocaleString()} tok
          </p>
        </div>

        <span className="shrink-0 text-[var(--text-tertiary)]">
          {expanded ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
        </span>
      </button>

      {expanded && (
        <div className="px-1 pb-3 grid grid-cols-2 gap-2 text-xs text-[var(--text-secondary)]">
          <div>
            <span className="text-[var(--text-tertiary)]">Input tokens: </span>
            {call.input_tokens.toLocaleString()}
          </div>
          <div>
            <span className="text-[var(--text-tertiary)]">Output tokens: </span>
            {call.output_tokens.toLocaleString()}
          </div>
          <div>
            <span className="text-[var(--text-tertiary)]">Duration: </span>
            {call.duration_ms ? `${call.duration_ms}ms` : "—"}
          </div>
          <div>
            <span className="text-[var(--text-tertiary)]">Cost: </span>
            ${call.cost_usd.toFixed(6)}
          </div>
          <div className="col-span-2">
            <span className="text-[var(--text-tertiary)]">Prompt hash: </span>
            <span className="font-mono">{call.system_prompt_hash || "—"}</span>
          </div>
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// Provider breakdown
// ═══════════════════════════════════════════════════════════════════════════

function ProviderBreakdown({ stats }: { stats: TransparencyStats }) {
  const entries = Object.entries(stats.by_provider || {});
  if (!entries.length) return null;

  return (
    <Card>
      <CardHeader><CardTitle>By Provider</CardTitle></CardHeader>
      <CardBody>
        <div className="space-y-2">
          {entries.map(([provider, data]) => (
            <div key={provider} className="flex items-center justify-between text-sm">
              <span className="capitalize text-[var(--text-primary)] font-medium">{provider}</span>
              <div className="flex items-center gap-4">
                <span className="text-[var(--text-tertiary)]">{data.calls} calls</span>
                <span className="font-mono text-[var(--text-primary)]">${data.cost.toFixed(4)}</span>
              </div>
            </div>
          ))}
        </div>
      </CardBody>
    </Card>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// Main page
// ═══════════════════════════════════════════════════════════════════════════

export function TransparencyPage() {
  const [stats, setStats] = useState<TransparencyStats | null>(null);
  const [calls, setCalls] = useState<TransparencyCall[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [offset, setOffset] = useState(0);
  const [hasMore, setHasMore] = useState(true);
  const [filterSource, setFilterSource] = useState("");
  const LIMIT = 50;

  const loadStats = useCallback(async () => {
    try {
      const s = await api.getTransparencyStats(30);
      setStats(s);
    } catch {
      // stats unavailable — transparency logger may not be wired yet
    }
  }, []);

  const loadCalls = useCallback(async (reset = false) => {
    const currentOffset = reset ? 0 : offset;
    if (reset) setLoading(true); else setLoadingMore(true);
    try {
      const result = await api.getTransparencyCalls({
        limit: LIMIT,
        offset: currentOffset,
        source: filterSource || undefined,
      });
      if (reset) {
        setCalls(result.calls);
        setOffset(LIMIT);
      } else {
        setCalls((prev) => [...prev, ...result.calls]);
        setOffset(currentOffset + LIMIT);
      }
      setHasMore(result.calls.length === LIMIT);
    } catch {
      // transparency not available
    }
    if (reset) setLoading(false); else setLoadingMore(false);
  }, [offset, filterSource]);

  useEffect(() => {
    loadStats();
    loadCalls(true);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filterSource]);

  const totalTokens = stats
    ? (stats.total_input_tokens + stats.total_output_tokens).toLocaleString()
    : "—";

  const sources = ["", "chat", "briefing", "onboarding", "proactive"];

  return (
    <div className="max-w-3xl mx-auto p-6 space-y-6">
      <header className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Shield className="h-5 w-5 text-[var(--brand-primary)]" />
            <h1 className="text-2xl font-bold text-[var(--text-primary)]">Transparency</h1>
          </div>
          <p className="text-sm text-[var(--text-secondary)]">
            Every LLM call your AI made — when, why, and what it cost.
          </p>
        </div>
        <Button variant="ghost" size="sm" onClick={() => { loadStats(); loadCalls(true); }}>
          <RefreshCw className="h-4 w-4" />
        </Button>
      </header>

      {/* Stats row */}
      {stats && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <StatCard
            label="Total calls"
            value={stats.total_calls.toLocaleString()}
            sub="last 30 days"
          />
          <StatCard
            label="Total cost"
            value={`$${stats.total_cost_usd.toFixed(4)}`}
            sub="last 30 days"
          />
          <StatCard
            label="Tokens used"
            value={totalTokens}
            sub="in + out"
          />
          <StatCard
            label="Data providers"
            value={String(Object.keys(stats.by_provider || {}).length)}
            sub="active"
          />
        </div>
      )}

      {/* Provider breakdown */}
      {stats && <ProviderBreakdown stats={stats} />}

      {/* Call log */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>LLM Call Log</CardTitle>
            <div className="flex gap-1">
              {sources.map((s) => (
                <button
                  key={s || "all"}
                  onClick={() => setFilterSource(s)}
                  className={cn(
                    "px-2 py-0.5 rounded text-xs transition-colors",
                    filterSource === s
                      ? "bg-[var(--brand-glow)] text-[var(--brand-primary)] font-medium"
                      : "text-[var(--text-tertiary)] hover:bg-[var(--bg-tertiary)]",
                  )}
                >
                  {s || "all"}
                </button>
              ))}
            </div>
          </div>
        </CardHeader>
        <CardBody className="p-0 px-3">
          {loading ? (
            <div className="space-y-3 py-4">
              {Array.from({ length: 5 }).map((_, i) => (
                <div key={i} className="h-10 rounded bg-[var(--bg-tertiary)] animate-skeleton" />
              ))}
            </div>
          ) : calls.length === 0 ? (
            <div className="py-8 text-center">
              <Shield className="h-8 w-8 text-[var(--text-tertiary)] mx-auto mb-2" />
              <p className="text-sm text-[var(--text-secondary)]">No LLM calls recorded yet.</p>
              <p className="text-xs text-[var(--text-tertiary)] mt-1">
                Calls appear here as you use OmniBrain.
              </p>
            </div>
          ) : (
            <>
              {calls.map((call) => (
                <CallRow key={call.id} call={call} />
              ))}
              {hasMore && (
                <div className="py-3 text-center">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => loadCalls(false)}
                    disabled={loadingMore}
                  >
                    {loadingMore ? "Loading…" : "Load more"}
                  </Button>
                </div>
              )}
            </>
          )}
        </CardBody>
      </Card>

      {/* Manifesto note */}
      <p className="text-xs text-[var(--text-tertiary)] text-center">
        OmniBrain manifesto — Layer 3: Transparency.
        Your AI works for you. You can always see exactly what it did and why.
      </p>
    </div>
  );
}
