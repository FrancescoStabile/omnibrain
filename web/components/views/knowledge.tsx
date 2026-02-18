/**
 * Knowledge — Three windows into what OmniBrain knows.
 *
 * Tab 1: Explore — entity cards (contacts, topics, orgs)
 * Tab 2: Graph   — interactive force-directed relationship graph (Canvas)
 * Tab 3: Search  — natural language query to the knowledge graph
 */

"use client";

import {
  useState,
  useCallback,
  useEffect,
  useRef,
  type KeyboardEvent,
} from "react";
import {
  Brain,
  Search,
  Network,
  Users,
  Clock,
  Loader2,
  Sparkles,
  LayoutGrid,
  TrendingUp,
  Mail,
  Building2,
  Tag,
  RefreshCw,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  api,
  type KnowledgeReference,
  type KnowledgeEntity,
  type KnowledgeGraphData,
  type GraphNode,
  type GraphEdge,
} from "@/lib/api";
import { Card, CardBody } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

// ═══════════════════════════════════════════════════════════════════════════
// Types
// ═══════════════════════════════════════════════════════════════════════════

type Tab = "explore" | "graph" | "search";

// ═══════════════════════════════════════════════════════════════════════════
// Tab Bar
// ═══════════════════════════════════════════════════════════════════════════

function TabBar({ active, onChange }: { active: Tab; onChange: (t: Tab) => void }) {
  const tabs: { id: Tab; label: string; icon: React.ReactNode }[] = [
    { id: "explore", label: "Explore", icon: <LayoutGrid className="h-4 w-4" /> },
    { id: "graph",   label: "Graph",   icon: <Network className="h-4 w-4" /> },
    { id: "search",  label: "Search",  icon: <Search className="h-4 w-4" /> },
  ];

  return (
    <div className="flex gap-1 p-1 rounded-[var(--radius-md)] bg-[var(--bg-secondary)] w-fit">
      {tabs.map((t) => (
        <button
          key={t.id}
          onClick={() => onChange(t.id)}
          className={cn(
            "flex items-center gap-1.5 px-4 py-2 rounded-[var(--radius-sm)] text-sm font-medium transition-all",
            active === t.id
              ? "bg-[var(--bg-primary)] text-[var(--text-primary)] shadow-sm"
              : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]",
          )}
        >
          {t.icon}
          {t.label}
        </button>
      ))}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// Entity Card
// ═══════════════════════════════════════════════════════════════════════════

function entityIcon(type: string) {
  if (type === "person") return <Users className="h-4 w-4" />;
  if (type === "organization") return <Building2 className="h-4 w-4" />;
  if (type === "topic") return <Tag className="h-4 w-4" />;
  return <Brain className="h-4 w-4" />;
}

function entityColor(type: string): string {
  if (type === "person") return "text-[var(--accent-blue)]";
  if (type === "organization") return "text-[var(--brand-primary)]";
  if (type === "topic") return "text-[var(--accent-orange)]";
  return "text-[var(--text-secondary)]";
}

function EntityCard({ entity }: { entity: KnowledgeEntity }) {
  const [expanded, setExpanded] = useState(false);
  const hasObservations = entity.observations && entity.observations.length > 0;

  return (
    <Card
      className="cursor-pointer transition-all hover:border-[var(--brand-primary)]/30"
      onClick={() => setExpanded((e) => !e)}
    >
      <CardBody className="p-4">
        <div className="flex items-start gap-3">
          <span className={cn("shrink-0 mt-0.5", entityColor(entity.type))}>
            {entityIcon(entity.type)}
          </span>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <span className="font-semibold text-sm text-[var(--text-primary)] truncate">
                {entity.name}
              </span>
              <Badge variant="default" className="capitalize shrink-0 text-[10px]">
                {entity.type}
              </Badge>
            </div>

            {entity.organization && (
              <p className="text-xs text-[var(--text-tertiary)] mb-1.5 truncate">
                {entity.organization}
              </p>
            )}

            <div className="flex items-center gap-3 text-xs text-[var(--text-tertiary)]">
              {entity.interaction_count > 0 && (
                <span className="flex items-center gap-1">
                  <Mail className="h-3 w-3" /> {entity.interaction_count}
                </span>
              )}
              {entity.last_seen && (
                <span className="flex items-center gap-1">
                  <Clock className="h-3 w-3" /> {new Date(entity.last_seen).toLocaleDateString()}
                </span>
              )}
              {entity.relationship_score != null && entity.relationship_score > 0 && (
                <span className="flex items-center gap-1">
                  <TrendingUp className="h-3 w-3" />
                  {Math.round(entity.relationship_score * 100)}%
                </span>
              )}
            </div>

            {expanded && hasObservations && (
              <div className="mt-3 space-y-1.5 border-t border-[var(--border-subtle)] pt-3">
                {entity.observations!.slice(0, 5).map((obs, i) => (
                  <div key={i} className="flex items-start gap-2">
                    <div className="shrink-0 w-1 h-1 rounded-full bg-[var(--brand-primary)] mt-1.5" />
                    <p className="text-xs text-[var(--text-secondary)] leading-relaxed">{obs}</p>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </CardBody>
    </Card>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// Explore Tab
// ═══════════════════════════════════════════════════════════════════════════

function ExploreTab() {
  const [entities, setEntities] = useState<KnowledgeEntity[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<"all" | "person" | "organization" | "topic">("all");
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<"interactions" | "recent" | "score">("interactions");
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const PAGE_SIZE = 24;

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.getKnowledgeEntities({
        type: filter === "all" ? undefined : filter,
        search: search || undefined,
        sort,
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      });
      setEntities(res.entities);
      setTotal(res.total);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load entities");
    } finally {
      setLoading(false);
    }
  }, [filter, search, sort, page]);

  useEffect(() => { load(); }, [load]);

  const filterTabs = [
    { id: "all" as const, label: "All" },
    { id: "person" as const, label: "People" },
    { id: "organization" as const, label: "Orgs" },
    { id: "topic" as const, label: "Topics" },
  ];

  return (
    <div className="space-y-5">
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-[var(--text-tertiary)]" />
          <input
            type="text"
            placeholder="Filter entities…"
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(0); }}
            className="w-full pl-9 pr-4 py-2 rounded-[var(--radius-md)] bg-[var(--bg-secondary)] border border-[var(--border-subtle)] text-sm text-[var(--text-primary)] placeholder:text-[var(--text-tertiary)] focus:outline-none focus:border-[var(--brand-primary)] transition-colors"
          />
        </div>
        <select
          value={sort}
          onChange={(e) => setSort(e.target.value as typeof sort)}
          className="px-3 py-2 rounded-[var(--radius-md)] bg-[var(--bg-secondary)] border border-[var(--border-subtle)] text-sm text-[var(--text-primary)] focus:outline-none"
        >
          <option value="interactions">Most interactions</option>
          <option value="recent">Most recent</option>
          <option value="score">Relationship score</option>
        </select>
      </div>

      <div className="flex gap-2">
        {filterTabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => { setFilter(tab.id); setPage(0); }}
            className={cn(
              "px-3 py-1.5 rounded-full text-xs font-medium transition-all",
              filter === tab.id
                ? "bg-[var(--brand-primary)] text-white"
                : "bg-[var(--bg-secondary)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]",
            )}
          >
            {tab.label}
          </button>
        ))}
        {total > 0 && (
          <span className="ml-auto text-xs text-[var(--text-tertiary)] self-center">
            {total} entities
          </span>
        )}
      </div>

      {loading && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="h-24 rounded-[var(--radius-lg)] bg-[var(--bg-secondary)] animate-pulse" />
          ))}
        </div>
      )}

      {error && !loading && (
        <div className="flex items-center gap-2 text-sm text-[var(--error)] p-4 rounded-[var(--radius-md)] bg-[color-mix(in_srgb,var(--error)_8%,transparent)]">
          {error}
          <button onClick={load} className="ml-auto underline">Retry</button>
        </div>
      )}

      {!loading && !error && entities.length > 0 && (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {entities.map((entity) => (
              <EntityCard key={`${entity.type}:${entity.name}`} entity={entity} />
            ))}
          </div>
          {total > PAGE_SIZE && (
            <div className="flex items-center justify-center gap-3 pt-2">
              <button
                disabled={page === 0}
                onClick={() => setPage((p) => p - 1)}
                className="px-4 py-2 rounded-[var(--radius-md)] bg-[var(--bg-secondary)] text-sm disabled:opacity-40 hover:bg-[var(--bg-tertiary)] transition-colors"
              >
                Prev
              </button>
              <span className="text-sm text-[var(--text-secondary)]">
                Page {page + 1} of {Math.ceil(total / PAGE_SIZE)}
              </span>
              <button
                disabled={(page + 1) * PAGE_SIZE >= total}
                onClick={() => setPage((p) => p + 1)}
                className="px-4 py-2 rounded-[var(--radius-md)] bg-[var(--bg-secondary)] text-sm disabled:opacity-40 hover:bg-[var(--bg-tertiary)] transition-colors"
              >
                Next
              </button>
            </div>
          )}
        </>
      )}

      {!loading && !error && entities.length === 0 && (
        <div className="py-16 text-center space-y-3">
          <Brain className="h-12 w-12 mx-auto text-[var(--text-tertiary)] opacity-40" />
          <p className="text-sm text-[var(--text-secondary)]">
            {search
              ? `No entities matching "${search}"`
              : "No entities yet — connect Google to build your knowledge graph"}
          </p>
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// Graph Tab — Canvas-based force-directed visualization
// ═══════════════════════════════════════════════════════════════════════════

interface SimNode extends GraphNode {
  x: number;
  y: number;
  vx: number;
  vy: number;
}

function nodeColor(type: string): string {
  if (type === "person") return "#6366f1";
  if (type === "organization") return "#f59e0b";
  if (type === "topic") return "#10b981";
  return "#6b7280";
}

function GraphTab() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [graphData, setGraphData] = useState<KnowledgeGraphData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [hovered, setHovered] = useState<string | null>(null);
  const animRef = useRef<number>(0);
  const simNodes = useRef<SimNode[]>([]);
  const tickCount = useRef(0);
  const W = 700, H = 500;

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getKnowledgeGraph(80);
      setGraphData(data);
      simNodes.current = data.nodes.map((n, i) => ({
        ...n,
        x: W / 2 + (W / 3) * Math.cos((i / data.nodes.length) * 2 * Math.PI),
        y: H / 2 + (H / 3) * Math.sin((i / data.nodes.length) * 2 * Math.PI),
        vx: (Math.random() - 0.5) * 2,
        vy: (Math.random() - 0.5) * 2,
      }));
      tickCount.current = 0;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load graph");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    if (!graphData || !canvasRef.current) return;
    const canvas = canvasRef.current;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const animate = () => {
      const ns = simNodes.current;
      if (!ns.length) { animRef.current = requestAnimationFrame(animate); return; }

      const alpha = Math.max(0.005, 0.35 * Math.pow(0.96, tickCount.current));
      tickCount.current++;

      for (let i = 0; i < ns.length; i++) {
        for (let j = i + 1; j < ns.length; j++) {
          const dx = ns[j].x - ns[i].x;
          const dy = ns[j].y - ns[i].y;
          const dist = Math.sqrt(dx * dx + dy * dy) || 1;
          const force = (5000 / (dist * dist)) * alpha;
          ns[i].vx -= (dx / dist) * force;
          ns[i].vy -= (dy / dist) * force;
          ns[j].vx += (dx / dist) * force;
          ns[j].vy += (dy / dist) * force;
        }
      }

      const nodeMap = new Map(ns.map((n) => [n.id, n]));
      for (const edge of graphData.edges) {
        const a = nodeMap.get(edge.source);
        const b = nodeMap.get(edge.target);
        if (!a || !b) continue;
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const dist = Math.sqrt(dx * dx + dy * dy) || 1;
        const stretch = (dist - 130) / dist;
        const force = stretch * 0.12 * alpha;
        a.vx += dx * force;
        a.vy += dy * force;
        b.vx -= dx * force;
        b.vy -= dy * force;
      }

      for (const n of ns) {
        n.vx += (W / 2 - n.x) * 0.003 * alpha;
        n.vy += (H / 2 - n.y) * 0.003 * alpha;
        n.vx *= 0.85;
        n.vy *= 0.85;
        n.x = Math.max(30, Math.min(W - 30, n.x + n.vx));
        n.y = Math.max(30, Math.min(H - 30, n.y + n.vy));
      }

      ctx.clearRect(0, 0, W, H);

      for (const edge of graphData.edges) {
        const a = nodeMap.get(edge.source);
        const b = nodeMap.get(edge.target);
        if (!a || !b) continue;
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.strokeStyle = "rgba(99,102,241,0.15)";
        ctx.lineWidth = Math.max(0.5, (edge.weight ?? 1) * 1.5);
        ctx.stroke();

        if (edge.label && (hovered === edge.source || hovered === edge.target)) {
          const mx = (a.x + b.x) / 2;
          const my = (a.y + b.y) / 2;
          ctx.font = "9px system-ui";
          ctx.fillStyle = "rgba(156,163,175,0.8)";
          ctx.textAlign = "center";
          ctx.fillText(edge.label, mx, my - 3);
        }
      }

      for (const n of ns) {
        const r = Math.max(6, Math.min(18, 6 + (n.weight ?? 1) * 2));
        const isHovered = hovered === n.id;
        if (isHovered) { ctx.shadowColor = nodeColor(n.type); ctx.shadowBlur = 12; }
        ctx.beginPath();
        ctx.arc(n.x, n.y, r, 0, Math.PI * 2);
        ctx.fillStyle = isHovered ? nodeColor(n.type) : `${nodeColor(n.type)}bb`;
        ctx.fill();
        ctx.strokeStyle = nodeColor(n.type);
        ctx.lineWidth = 1.5;
        ctx.stroke();
        ctx.shadowBlur = 0;
        ctx.font = `${isHovered ? "bold " : ""}11px system-ui`;
        ctx.fillStyle = isHovered ? "rgba(255,255,255,0.95)" : "rgba(229,231,235,0.7)";
        ctx.textAlign = "center";
        ctx.fillText(
          n.label.length > 14 ? n.label.slice(0, 12) + "…" : n.label,
          n.x, n.y + r + 13,
        );
      }

      animRef.current = requestAnimationFrame(animate);
    };

    animRef.current = requestAnimationFrame(animate);
    return () => { if (animRef.current) cancelAnimationFrame(animRef.current); };
  }, [graphData, hovered]);

  const handleMouseMove = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!canvasRef.current) return;
    const rect = canvasRef.current.getBoundingClientRect();
    const mx = (e.clientX - rect.left) * (W / rect.width);
    const my = (e.clientY - rect.top) * (H / rect.height);
    let closest: string | null = null;
    let minDist = 20;
    for (const n of simNodes.current) {
      const d = Math.sqrt((n.x - mx) ** 2 + (n.y - my) ** 2);
      if (d < minDist) { minDist = d; closest = n.id; }
    }
    setHovered(closest);
  }, []);

  const legendItems = [
    { type: "person", label: "Person", color: "#6366f1" },
    { type: "organization", label: "Org", color: "#f59e0b" },
    { type: "topic", label: "Topic", color: "#10b981" },
  ];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          {legendItems.map((item) => (
            <div key={item.type} className="flex items-center gap-1.5 text-xs text-[var(--text-secondary)]">
              <div className="w-3 h-3 rounded-full" style={{ backgroundColor: item.color }} />
              {item.label}
            </div>
          ))}
        </div>
        <div className="flex items-center gap-2">
          {graphData && (
            <span className="text-xs text-[var(--text-tertiary)]">
              {graphData.nodes.length} nodes · {graphData.edges.length} edges
            </span>
          )}
          <button
            onClick={load}
            className="p-1.5 rounded-[var(--radius-sm)] text-[var(--text-tertiary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-secondary)] transition-all"
          >
            <RefreshCw className="h-4 w-4" />
          </button>
        </div>
      </div>

      {loading && (
        <div className="flex items-center justify-center h-64 gap-3 text-[var(--text-secondary)]">
          <Loader2 className="h-5 w-5 animate-spin text-[var(--brand-primary)]" />
          <span className="text-sm">Building graph…</span>
        </div>
      )}

      {error && !loading && (
        <div className="flex flex-col items-center justify-center h-64 gap-3 text-[var(--text-secondary)]">
          <Network className="h-12 w-12 opacity-30" />
          <p className="text-sm">{error}</p>
          <button onClick={load} className="text-xs text-[var(--brand-primary)] underline">Retry</button>
        </div>
      )}

      {!loading && !error && graphData && graphData.nodes.length > 0 && (
        <div className="relative rounded-[var(--radius-lg)] overflow-hidden border border-[var(--border-subtle)] bg-[var(--bg-secondary)]">
          <canvas
            ref={canvasRef}
            width={W}
            height={H}
            onMouseMove={handleMouseMove}
            onMouseLeave={() => setHovered(null)}
            className="w-full block cursor-crosshair"
            style={{ maxHeight: "500px" }}
          />
          {hovered && (
            <div className="absolute bottom-3 left-3 px-3 py-1.5 rounded-[var(--radius-sm)] bg-[var(--bg-primary)]/80 border border-[var(--border-subtle)] text-xs text-[var(--text-primary)] backdrop-blur-sm">
              {simNodes.current.find((n) => n.id === hovered)?.label}
            </div>
          )}
        </div>
      )}

      {!loading && !error && graphData && graphData.nodes.length === 0 && (
        <div className="flex flex-col items-center justify-center h-64 gap-3 text-[var(--text-secondary)]">
          <Network className="h-12 w-12 opacity-30" />
          <p className="text-sm">No graph data yet. Connect Google to build your knowledge graph.</p>
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// Search Tab — natural language query
// ═══════════════════════════════════════════════════════════════════════════

const exampleQueries = [
  "What do I know about pricing discussions?",
  "What did my recent emails discuss?",
  "Show patterns in my meetings",
  "Who contacted me most recently?",
];

function SearchTab() {
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<{
    summary: string;
    references: KnowledgeReference[];
    source_count?: number;
    error?: string;
  } | null>(null);
  const [history, setHistory] = useState<string[]>([]);

  const search = useCallback(async (q?: string) => {
    const sq = (q || query).trim();
    if (!sq) return;
    setLoading(true);
    setResult(null);
    try {
      const res = await api.queryKnowledge(sq);
      setResult(res);
      setHistory((prev) => [sq, ...prev.filter((h) => h !== sq)].slice(0, 10));
    } catch (e) {
      setResult({ summary: "", references: [], error: e instanceof Error ? e.message : "Query failed" });
    } finally {
      setLoading(false);
    }
  }, [query]);

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); search(); }
  };

  return (
    <div className="space-y-5">
      <div className="flex gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-[var(--text-tertiary)]" />
          <Input
            placeholder="Ask anything about your knowledge graph…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            className="pl-9"
          />
        </div>
        <Button onClick={() => search()} disabled={loading || !query.trim()}>
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
        </Button>
      </div>

      {!result && !loading && (
        <div className="space-y-5">
          <div>
            <p className="text-xs font-medium text-[var(--text-tertiary)] uppercase tracking-wide mb-2">Try asking…</p>
            <div className="flex flex-wrap gap-2">
              {exampleQueries.map((eq) => (
                <button
                  key={eq}
                  onClick={() => { setQuery(eq); search(eq); }}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-[var(--bg-secondary)] border border-[var(--border-subtle)] text-xs text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-all"
                >
                  <Sparkles className="h-3 w-3 text-amber-400" /> {eq}
                </button>
              ))}
            </div>
          </div>
          {history.length > 0 && (
            <div>
              <p className="text-xs font-medium text-[var(--text-tertiary)] uppercase tracking-wide mb-2">Recent</p>
              <div className="flex flex-wrap gap-2">
                {history.map((h) => (
                  <button
                    key={h}
                    onClick={() => { setQuery(h); search(h); }}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-[var(--bg-secondary)] border border-[var(--border-subtle)] text-xs text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-all"
                  >
                    <Clock className="h-3 w-3" /> {h}
                  </button>
                ))}
              </div>
            </div>
          )}
          <div className="py-8 text-center space-y-2">
            <Brain className="h-12 w-12 mx-auto text-[var(--text-tertiary)] opacity-30" />
            <p className="text-sm font-medium text-[var(--text-secondary)]">Natural language knowledge search</p>
            <p className="text-xs text-[var(--text-tertiary)]">Ask questions about your emails, contacts, meetings, and patterns.</p>
          </div>
        </div>
      )}

      {loading && (
        <div className="flex items-center gap-3 py-8 text-[var(--text-secondary)]">
          <Loader2 className="h-5 w-5 animate-spin text-[var(--brand-primary)]" />
          <span className="text-sm">Searching knowledge graph…</span>
        </div>
      )}

      {result && !loading && (
        <div className="space-y-4">
          {result.error && (
            <div className="p-4 rounded-[var(--radius-md)] bg-[color-mix(in_srgb,var(--error)_8%,transparent)] text-sm text-[var(--error)]">
              {result.error}
            </div>
          )}
          {result.summary && (
            <Card>
              <CardBody className="p-4">
                <div className="flex items-start gap-3">
                  <Brain className="h-5 w-5 text-[var(--brand-primary)] shrink-0 mt-0.5" />
                  <div className="flex-1 min-w-0">
                    <div className="prose prose-sm dark:prose-invert max-w-none text-[var(--text-primary)]">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{result.summary}</ReactMarkdown>
                    </div>
                    {result.source_count != null && (
                      <p className="mt-2 text-xs text-[var(--text-tertiary)]">Based on {result.source_count} sources</p>
                    )}
                  </div>
                </div>
              </CardBody>
            </Card>
          )}
          {result.references.length > 0 && (
            <div>
              <h3 className="text-xs font-medium text-[var(--text-tertiary)] uppercase tracking-wide mb-2">References</h3>
              <div className="space-y-2">
                {result.references.map((ref, i) => (
                  <Card key={i} className="hover:border-[var(--brand-primary)]/20 transition-colors">
                    <CardBody className="p-3">
                      <div className="prose prose-sm dark:prose-invert max-w-none text-[var(--text-secondary)]">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>{ref.text}</ReactMarkdown>
                      </div>
                      <div className="mt-1.5 flex items-center gap-2">
                        <Badge className="text-[10px]">{ref.source}</Badge>
                        {ref.date && <span className="text-xs text-[var(--text-tertiary)]">{ref.date}</span>}
                        {ref.score != null && <span className="text-xs text-[var(--text-tertiary)]">{Math.round(ref.score * 100)}% relevant</span>}
                      </div>
                    </CardBody>
                  </Card>
                ))}
              </div>
            </div>
          )}
          {!result.error && !result.summary && result.references.length === 0 && (
            <div className="py-8 text-center text-[var(--text-secondary)]">
              <p className="text-sm">No results found. Try rephrasing your query.</p>
            </div>
          )}
          <button onClick={() => setResult(null)} className="text-xs text-[var(--text-tertiary)] hover:text-[var(--text-primary)] underline">
            ← New search
          </button>
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// Main KnowledgePage
// ═══════════════════════════════════════════════════════════════════════════

export function KnowledgePage() {
  const [tab, setTab] = useState<Tab>("explore");

  return (
    <div className="max-w-4xl mx-auto p-6 space-y-6">
      <header>
        <h1 className="text-2xl font-bold text-[var(--text-primary)]">Knowledge Graph</h1>
        <p className="text-sm text-[var(--text-secondary)] mt-1">
          Explore everything OmniBrain has learned about your world.
        </p>
      </header>

      <TabBar active={tab} onChange={setTab} />

      {tab === "explore" && <ExploreTab />}
      {tab === "graph"   && <GraphTab />}
      {tab === "search"  && <SearchTab />}
    </div>
  );
}

