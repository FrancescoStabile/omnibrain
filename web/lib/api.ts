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

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  timestamp: string;
  actions?: ChatAction[];
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

// ═══════════════════════════════════════════════════════════════════════════
// Fetch wrapper
// ═══════════════════════════════════════════════════════════════════════════

class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const url = `${BASE}${path}`;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };

  const res = await fetch(url, { ...options, headers });

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
};

// ═══════════════════════════════════════════════════════════════════════════
// Chat streaming (SSE-like fetch with ReadableStream)
// ═══════════════════════════════════════════════════════════════════════════

export async function* streamChat(
  message: string,
  sessionId?: string,
): AsyncGenerator<{ type: string; content?: string; action?: ChatAction; session_id?: string }> {
  const res = await fetch(`${BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, session_id: sessionId, stream: true }),
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
}
