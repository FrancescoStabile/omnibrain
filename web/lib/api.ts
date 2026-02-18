/**
 * OmniBrain API Client
 *
 * Typed client for the FastAPI backend. All calls go through /api
 * which Next.js rewrites to the Python server.
 */

const BASE = "/api/v1";

// ═══════════════════════════════════════════════════════════════════════════
// Types — match the FastAPI Pydantic models + API-SPEC.md
// ═══════════════════════════════════════════════════════════════════════════

export interface Status {
  version: string;
  uptime_seconds: number;
  stats: Record<string, number>;
  engine: Record<string, unknown>;
}

export interface Briefing {
  id: number;
  date: string;
  type: string;
  content: string;
  events_processed: number;
  actions_proposed: number;
}

// ── Structured Briefing (card-based view) ──

export interface EmailSection {
  total: number;
  unread: number;
  urgent: number;
  needs_response: number;
  drafts_ready: number;
  top_senders: string[];
}

export interface CalendarEventItem {
  title: string;
  time: string;
  attendees: number;
  duration: number;
}

export interface CalendarSection {
  total_events: number;
  total_hours: number;
  next_meeting: string;
  next_meeting_time: string;
  events: CalendarEventItem[];
  conflicts: string[];
}

export interface ProposalSection {
  total_pending: number;
  by_type: Record<string, number>;
  high_priority: { type: string; title: string; priority: number }[];
}

export interface PriorityItem {
  rank: number;
  title: string;
  reason: string;
  source: string;
}

export interface BriefingData {
  date: string;
  briefing_type: string;
  greeting: string;
  emails: EmailSection;
  calendar: CalendarSection;
  proposals: ProposalSection;
  priorities: PriorityItem[];
  observations: string[];
  memory_highlights: string[];
  content: string;
}

export interface Proposal {
  id: number;
  type: string;
  title: string;
  description: string;
  priority: number;
  status: string;
  created_at: string;
}

export interface SearchResult {
  id: string;
  text: string;
  source: string;
  source_type: string;
  score: number;
}

export interface SearchResponse {
  query: string;
  results: SearchResult[];
  count: number;
}

export interface Contact {
  email: string;
  name: string;
  relationship: string;
  organization: string;
  interaction_count: number;
}

export interface SkillInfo {
  name: string;
  version: string;
  description: string;
  author: string;
  category: string;
  icon: string;
  permissions: string[];
  enabled: boolean;
  installed: boolean;
}

export interface MarketplaceSkill {
  name: string;
  version: string;
  description: string;
  author: string;
  repo: string;
  downloads: number;
  stars: number;
  verified: boolean;
  icon: string;
  category: string;
  permissions: string[];
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  timestamp: string;
  actions?: ChatAction[];
  references?: KnowledgeReference[];
  suggested_followups?: string[];
}

export interface ChatAction {
  type: string;
  title: string;
  data?: Record<string, unknown>;
}

export interface ChatSession {
  session_id: string;
  message_count: number;
  started_at: string;
  last_message_at: string;
}

export interface TimelineItem {
  id: string;
  type: "event" | "proposal" | "observation";
  source: string;
  title: string;
  timestamp: string;
  metadata: string;
  // Detail fields (populated when available)
  description?: string;
  sender?: string;
  location?: string;
  attendees?: string[];
  proposal_id?: number;
  references?: KnowledgeReference[];
}

export interface KnowledgeReference {
  text: string;
  source: string;
  date?: string;
  score?: number;
}

export interface Pattern {
  type: string;
  description: string;
  occurrences?: number;
  confidence?: number;
  strength: string;
  first_seen?: string;
  last_seen?: string;
}

export interface Automation {
  title: string;
  description: string;
  pattern_type: string;
  confidence: number;
}

export interface Settings {
  profile: {
    name: string;
    timezone: string;
    language: string;
  };
  notifications: Record<string, boolean | Record<string, string>>;
  llm: {
    primary_provider: string;
    fallback_provider: string;
    monthly_budget: number;
    current_month_cost: number;
  };
  appearance: {
    theme: string;
  };
}

// ── OAuth + Onboarding types ──

export interface OAuthStatus {
  connected: boolean;
  email: string;
  name: string;
  scopes: string[];
  has_client_credentials: boolean;
}

export interface InsightCard {
  icon: string;
  title: string;
  body: string;
  action: string;
  action_type: string;
  priority: number;
}

export interface OnboardingResult {
  greeting: string;
  stats: Record<string, number>;
  insights: InsightCard[];
  user_email: string;
  user_name: string;
  completed_at: string;
  duration_ms: number;
}

export interface TransparencyCall {
  id: string;
  timestamp: string;
  provider: string;
  model: string;
  source: string;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  duration_ms: number;
  had_tools: boolean;
  had_error: boolean;
  system_prompt_hash: string;
}

export interface TransparencyStats {
  total_calls: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_cost_usd: number;
  by_provider: Record<string, { calls: number; cost: number }>;
  by_source: Record<string, { calls: number; cost: number }>;
}

export interface TransparencyDailyEntry {
  date: string;
  calls: number;
  cost_usd: number;
  input_tokens: number;
  output_tokens: number;
}

// ── Brain Status ──

export interface BrainStatus {
  uptime_seconds: number;
  emails_analyzed: number;
  contacts_mapped: number;
  patterns_detected: number;
  memories_stored: number;
  skills_active: number;
  llm_provider: string;
  month_cost_usd: number;
  recent_insights: string[];
  learning_progress: number;
  google_connected: boolean;
  stats: Record<string, number>;
}

// ── Knowledge Entities ──

export interface KnowledgeEntity {
  id: string;
  name: string;
  type: "person" | "company" | "topic" | "project";
  email?: string;
  organization?: string;
  interaction_count: number;
  last_seen?: string;
  relationship?: string;
}

export interface KnowledgeEntitiesResponse {
  entities: KnowledgeEntity[];
  total: number;
  offset: number;
  limit: number;
}

// ── Knowledge Graph ──

export interface GraphNode {
  id: string;
  label: string;
  type: "person" | "topic" | "company";
  val?: number;
  organization?: string;
  relationship?: string;
}

export interface GraphEdge {
  source: string;
  target: string;
  type: string;
}

export interface KnowledgeGraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
  node_count: number;
  edge_count: number;
}

// ── Contact Detail ──

export interface ContactDetail {
  contact: Contact & { last_seen?: string };
  emails: { count: number; recent: { id: string; subject: string; timestamp: string; snippet: string }[] };
  meetings: { count: number; recent: { id: string; title: string; timestamp: string; attendee_count: number }[] };
  topics: string[];
  relationship_score: number;
}

// ── Demo Mode ──

export interface DemoStatus {
  active: boolean;
  record_count: number;
  contacts: number;
  events: number;
  proposals: number;
  patterns: number;
}


// ═══════════════════════════════════════════════════════════════════════════
// Fetch wrapper with retry + timeout
// ═══════════════════════════════════════════════════════════════════════════

export type ErrorKind =
  | "backend_down"
  | "google_disconnected"
  | "no_api_key"
  | "rate_limited"
  | "server_error"
  | "not_found"
  | "generic";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }

  /** Classify this error for contextual recovery UI */
  get kind(): ErrorKind {
    // Network errors / timeout → backend is unreachable
    if (this.status === 0) return "backend_down";
    // Rate limiting
    if (this.status === 429) return "rate_limited";
    // OAuth / Google disconnected
    if (
      this.code === "GOOGLE_NOT_CONNECTED" ||
      this.code === "OAUTH_REQUIRED" ||
      (this.status === 403 && /oauth|google|token/i.test(this.message))
    ) return "google_disconnected";
    // Missing API key
    if (
      this.code === "NO_API_KEY" ||
      this.code === "INVALID_API_KEY" ||
      (this.status === 401 && /api.key/i.test(this.message))
    ) return "no_api_key";
    // Server errors
    if (this.status >= 500) return "server_error";
    // Not found
    if (this.status === 404) return "not_found";
    return "generic";
  }
}

/** Global error listener — set by UI layer for toast notifications */
let _onApiError: ((error: ApiError) => void) | null = null;
export function setApiErrorHandler(fn: ((error: ApiError) => void) | null) {
  _onApiError = fn;
}

const MAX_RETRIES = 2;
const RETRY_DELAY = 800; // ms
const REQUEST_TIMEOUT = 15_000; // 15s

async function request<T>(
  path: string,
  options: RequestInit = {},
  { retries = MAX_RETRIES, silent = false }: { retries?: number; silent?: boolean } = {},
): Promise<T> {
  const url = `${BASE}${path}`;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };

  let lastError: ApiError | null = null;

  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT);

      const res = await fetch(url, {
        ...options,
        headers,
        signal: controller.signal,
      });

      clearTimeout(timeout);

      if (!res.ok) {
        let code = "UNKNOWN";
        let message = res.statusText;
        try {
          const body = await res.json();
          code = body.error?.code || body.detail || code;
          message = body.error?.message || body.detail || message;
        } catch {
          // response wasn't JSON
        }
        throw new ApiError(res.status, code, message);
      }

      return res.json() as Promise<T>;
    } catch (err) {
      if (err instanceof ApiError) {
        // Don't retry 4xx (client errors) except 429 (rate limit)
        if (err.status >= 400 && err.status < 500 && err.status !== 429) {
          lastError = err;
          break;
        }
        lastError = err;
      } else if (err instanceof DOMException && err.name === "AbortError") {
        lastError = new ApiError(0, "TIMEOUT", "Request timed out");
      } else {
        lastError = new ApiError(0, "NETWORK", "Network error — is the backend running?");
      }

      // Wait before retry (skip wait on last attempt)
      if (attempt < retries) {
        await new Promise((r) => setTimeout(r, RETRY_DELAY * (attempt + 1)));
      }
    }
  }

  // Notify global error handler
  if (lastError && !silent && _onApiError) {
    _onApiError(lastError);
  }

  throw lastError!;
}

// ═══════════════════════════════════════════════════════════════════════════
// API methods
// ═══════════════════════════════════════════════════════════════════════════

export const api = {
  // ── Status ──
  getStatus: () => request<Status>("/status"),

  // ── Briefing ──
  getBriefing: (type = "morning") =>
    request<Briefing>(`/briefing?type=${type}`),

  generateBriefing: (type = "morning") =>
    request<Briefing>(`/briefing/generate?type=${type}`, { method: "POST" }),

  getBriefingData: (type = "morning") =>
    request<BriefingData>(`/briefing/data?type=${type}`),

  // ── Proposals ──
  getProposals: (status = "pending") =>
    request<Proposal[]>(`/proposals?status=${status}`),

  approveProposal: (id: number) =>
    request<{ ok: boolean }>(`/proposals/${id}/approve`, { method: "POST" }),

  rejectProposal: (id: number, reason = "") =>
    request<{ ok: boolean }>(`/proposals/${id}/reject`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    }),

  snoozeProposal: (id: number, hours = 4) =>
    request<{ ok: boolean }>(`/proposals/${id}/snooze`, {
      method: "POST",
      body: JSON.stringify({ hours }),
    }),

  // ── Memory / Search ──
  search: (q: string, limit = 10) =>
    request<SearchResponse>(`/search?q=${encodeURIComponent(q)}&limit=${limit}`),

  // ── Chat ──
  sendMessage: (text: string, sessionId?: string) =>
    request<{ response: string; source: string }>("/message", {
      method: "POST",
      body: JSON.stringify({ text, session_id: sessionId }),
    }),

  // ── Skills ──
  getSkills: () => request<{ skills: SkillInfo[] }>("/skills"),

  installSkill: (name: string) =>
    request<{ status: string }>(`/skills/${name}/install`, { method: "POST" }),

  removeSkill: (name: string) =>
    request<{ status: string }>(`/skills/${name}`, { method: "DELETE" }),

  enableSkill: (name: string) =>
    request<{ ok: boolean }>(`/skills/${name}/enable`, { method: "POST" }),

  disableSkill: (name: string) =>
    request<{ ok: boolean }>(`/skills/${name}/disable`, { method: "POST" }),

  getSkillRuntime: () =>
    request<{ skills: Record<string, { enabled: boolean; loaded: boolean }> }>("/skills/runtime"),

  // ── Marketplace ──
  browseMarketplace: (search = "", category = "") => {
    const q = new URLSearchParams();
    if (search) q.set("search", search);
    if (category) q.set("category", category);
    return request<{ skills: MarketplaceSkill[]; total: number }>(`/marketplace/browse?${q}`);
  },

  installFromMarketplace: (repo: string) =>
    request<{ status: string; name: string; message: string }>("/marketplace/install", {
      method: "POST",
      body: JSON.stringify({ repo }),
    }),

  // ── Settings ──
  getSettings: () => request<Settings>("/settings"),

  updateSettings: (settings: Partial<Settings>) =>
    request<Settings>("/settings", {
      method: "PUT",
      body: JSON.stringify(settings),
    }),

  // ── Chat sessions & history ──
  getChatSessions: (limit = 20) =>
    request<{ sessions: ChatSession[] }>(`/chat/sessions?limit=${limit}`),

  getChatHistory: (sessionId = "default", limit = 100) =>
    request<{ session_id: string; messages: ChatMessage[] }>(
      `/chat/history?session_id=${encodeURIComponent(sessionId)}&limit=${limit}`,
    ),

  deleteChatSession: (sessionId: string) =>
    request<{ ok: boolean; deleted: number }>(`/chat/sessions/${encodeURIComponent(sessionId)}`, {
      method: "DELETE",
    }),

  // ── Stats ──
  getStats: () => request<Record<string, number>>("/stats"),

  // ── Contacts ──
  getContacts: (limit = 100) =>
    request<Contact[]>(`/contacts?limit=${limit}`),

  // ── Timeline ──
  getTimeline: (params: { source?: string; since?: string; until?: string; limit?: number; offset?: number } = {}) => {
    const q = new URLSearchParams();
    if (params.source) q.set("source", params.source);
    if (params.since) q.set("since", params.since);
    if (params.until) q.set("until", params.until);
    if (params.limit) q.set("limit", String(params.limit));
    if (params.offset) q.set("offset", String(params.offset));
    return request<{ items: TimelineItem[]; total: number; offset: number; limit: number }>(`/timeline?${q}`);
  },

  // ── Knowledge ──
  queryKnowledge: (q: string) =>
    request<{ summary: string; references: KnowledgeReference[]; source_count?: number; error?: string }>(
      `/knowledge/query?q=${encodeURIComponent(q)}`
    ),

  getKnowledgeContact: (identifier: string) =>
    request<Record<string, unknown>>(`/knowledge/contact/${encodeURIComponent(identifier)}`),

  // ── Patterns ──
  getPatterns: () =>
    request<{ patterns: Pattern[]; strong_patterns: Pattern[]; automations: Automation[]; summary: Record<string, unknown> }>(
      "/patterns"
    ),

  // ── OAuth ──
  getOAuthUrl: (scope = "gmail+calendar") => {
    const redirect = typeof window !== "undefined" ? window.location.origin : "";
    return request<{ auth_url: string }>(
      `/oauth/google?scope=${scope}&redirect=${encodeURIComponent(redirect)}`
    );
  },

  getOAuthStatus: () => request<OAuthStatus>("/oauth/status"),

  disconnectGoogle: () =>
    request<{ disconnected: boolean }>("/oauth/disconnect", { method: "POST" }),

  // ── Onboarding ──
  analyzeOnboarding: () =>
    request<OnboardingResult>("/onboarding/analyze", { method: "POST" }),

  saveOnboardingProfile: (profile: { name?: string; work?: string; goals?: string; timezone?: string }) =>
    request<{ ok: boolean; saved: Record<string, string> }>("/onboarding/profile", {
      method: "POST",
      body: JSON.stringify(profile),
    }),

  // ── Transparency ──
  getTransparencyCalls: (params: { limit?: number; offset?: number; provider?: string; source?: string } = {}) => {
    const q = new URLSearchParams();
    if (params.limit) q.set("limit", String(params.limit));
    if (params.offset) q.set("offset", String(params.offset));
    if (params.provider) q.set("provider", params.provider);
    if (params.source) q.set("source", params.source);
    return request<{ calls: TransparencyCall[]; limit: number; offset: number }>(`/transparency/calls?${q}`);
  },

  getTransparencyStats: (days = 30) =>
    request<TransparencyStats>(`/transparency/stats?days=${days}`),

  getTransparencyDaily: (days = 30) =>
    request<{ days: number; data: TransparencyDailyEntry[] }>(`/transparency/daily?days=${days}`),

  // ── Brain Status ──
  getBrainStatus: () =>
    request<BrainStatus>("/brain-status", {}, { silent: true }),

  // ── Knowledge Entities + Graph ──
  getKnowledgeEntities: (params: { type?: string; sort?: string; limit?: number; offset?: number } = {}) => {
    const q = new URLSearchParams();
    if (params.type) q.set("type", params.type);
    if (params.sort) q.set("sort", params.sort);
    if (params.limit) q.set("limit", String(params.limit));
    if (params.offset) q.set("offset", String(params.offset));
    return request<KnowledgeEntitiesResponse>(`/knowledge/entities?${q}`);
  },

  getKnowledgeGraph: (limit = 100) =>
    request<KnowledgeGraphData>(`/knowledge/graph?limit=${limit}`, {}, { silent: true }),

  // ── Contact Detail ──
  getContactDetail: (email: string) =>
    request<ContactDetail>(`/contacts/${encodeURIComponent(email)}/detail`),

  // ── Demo Mode ──
  getDemoStatus: () =>
    request<DemoStatus>("/data/demo/status", {}, { silent: true }),

  activateDemo: () =>
    request<{ activated: boolean; records_inserted: number }>("/data/demo/activate", { method: "POST" }),

  deactivateDemo: () =>
    request<{ deactivated: boolean; records_removed: number }>("/data/demo/deactivate", { method: "POST" }),

  // ── Data export / wipe ──
  exportDataUrl: () => `${BASE}/data/export`,  // Use directly in <a href> for streaming download

  requestDataWipe: () =>
    request<{ status: string; confirmation_token: string; message: string; expires_in: number }>("/data/wipe", {
      method: "POST",
    }),

  confirmDataWipe: (confirmationToken: string) =>
    request<{ status: string; message: string }>("/data/wipe", {
      method: "DELETE",
      body: JSON.stringify({ confirmation_token: confirmationToken }),
    }),
};

// ═══════════════════════════════════════════════════════════════════════════
// Onboarding SSE stream
// ═══════════════════════════════════════════════════════════════════════════

export type OnboardingEvent =
  | { type: "progress"; step: string; message: string; count?: number }
  | { type: "insight"; icon: string; title: string; body: string; action?: string; action_type?: string; priority?: number }
  | { type: "result" } & OnboardingResult
  | { type: "error"; message: string };

/**
 * Stream onboarding analysis via SSE.
 * Each event is yielded as it arrives — progress updates, then insight
 * cards one by one, then the final OnboardingResult.
 */
export async function* streamOnboarding(): AsyncGenerator<OnboardingEvent> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 60_000);

  try {
    const res = await fetch(`${BASE}/onboarding/analyze/stream`, {
      signal: controller.signal,
    });

    if (!res.ok) {
      throw new ApiError(res.status, "STREAM_ERROR", "Onboarding stream failed");
    }

    const reader = res.body?.getReader();
    if (!reader) return;

    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        const trimmed = line.trim();
        if (trimmed.startsWith("data: ")) {
          try {
            yield JSON.parse(trimmed.slice(6));
          } catch {
            // skip malformed
          }
        }
      }
    }

    if (buffer.trim().startsWith("data: ")) {
      try {
        yield JSON.parse(buffer.trim().slice(6));
      } catch {
        // skip malformed tail
      }
    }
  } finally {
    clearTimeout(timeout);
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// Chat streaming (SSE-like fetch with ReadableStream)
// ═══════════════════════════════════════════════════════════════════════════

export async function* streamChat(
  message: string,
  sessionId?: string,
): AsyncGenerator<{ type: string; content?: string; action?: ChatAction; session_id?: string }> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 120_000);

  try {
    const res = await fetch(`${BASE}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, session_id: sessionId, stream: true }),
      signal: controller.signal,
    });

    if (!res.ok) {
      throw new ApiError(res.status, "STREAM_ERROR", "Chat stream failed");
    }

    const reader = res.body?.getReader();
    if (!reader) return;

    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        const trimmed = line.trim();
        if (trimmed.startsWith("data: ")) {
          try {
            const data = JSON.parse(trimmed.slice(6));
            yield data;
          } catch {
            // Skip malformed lines
          }
        }
      }
    }

    // Flush remaining buffer
    if (buffer.trim().startsWith("data: ")) {
      try {
        const data = JSON.parse(buffer.trim().slice(6));
        yield data;
      } catch {
        // Skip malformed tail
      }
    }
  } finally {
    clearTimeout(timeout);
  }
}
