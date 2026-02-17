# OmniBrain — Master Evolution Plan

**Date:** 18 February 2026
**Goal:** From current state → Perfect product ready for public launch
**Guiding Star:** manifesto.md is the single source of truth

---

## Current State Assessment

### What Works
- **Omnigent engine**: Complete ReAct agent, reasoning graph, planner, reflection, cost tracking — 1474 tests passing
- **5 built-in Skills**: email-manager, calendar-assistant, morning-briefing, memory-search, pattern-detector — all functional
- **Web UI skeleton**: 6/10 manifesto screens present (Home, Chat, Briefing, Skills, Settings, Notifications)
- **Database layer**: SQLite + FTS5 + WAL, GDPR export/wipe
- **LLM Router**: Multi-provider (DeepSeek, Claude, OpenAI, Ollama) with auto-fallback
- **Memory system**: Dual-backend (SQLite FTS5 always + ChromaDB optional)
- **Knowledge Graph**: Entity-relationship queries, who_said_what, correlate, timeline
- **Proactive Engine**: Pattern detection, morning/evening/weekly tasks
- **OAuth**: Google OAuth for Gmail + Calendar
- **Conversation Extractor**: LLM-powered structured data extraction from chat

### What's Broken (41 issues found)
- **P0 Critical Bugs**: 5
- **P1 Security Gaps**: 6
- **P2 Missing Features**: 11
- **P3 Quality Issues**: 9
- **Frontend Bugs**: 10

### Dead Code: ~1,172 lines across 3 modules
- `context_resurrection.py` (440 LOC) — never imported
- `prompt_injection.py` (301 LOC) — never used in production
- `approval.py` (431 LOC) — never wired

---

## Phase 0: TRIAGE — Fix What's Visibly Broken
**Priority:** Immediate — users see these bugs right now
**Estimated effort:** 1 day
**Files:** db.py, briefing.py, conversation_extractor.py, daemon.py

### 0.1 Calendar Events Not Filtered by Date
**Bug:** `_collect_calendar()` in briefing.py calls `get_events(source="calendar", limit=30)` with NO date filter. "Today's Calendar" shows events from all time.
**Fix:**
1. Add `since` parameter to `_collect_calendar()` — pass `datetime.now().replace(hour=0, minute=0)`
2. Add `until` parameter — pass `datetime.now().replace(hour=23, minute=59)`
3. Same fix for `_collect_emails()` — filter to last 24h only
4. Update `get_events()` in db.py to support `until` parameter

### 0.2 "00:00" Timestamps on Chat-Extracted Events
**Bug:** conversation_extractor.py defaults extracted events to `T00:00:00` when no time is specified. Briefing shows "00:00" for "meeting tomorrow" without a time.
**Fix:**
1. In conversation_extractor.py extraction prompt: instruct LLM to use `null` for time when not specified (not midnight)
2. In `extract_and_persist()`: if time component is midnight, store as all-day event with `metadata.all_day = true`
3. In briefing.py `EventRow`: render "All day" instead of "00:00" when `all_day` flag is set
4. In frontend briefing.tsx: display "All day" when `event.time === "00:00"` or `event.all_day === true`

### 0.3 Event Duplication — No UNIQUE Constraint
**Bug:** Every daemon poll cycle re-inserts ALL calendar events. After a few hours, events table is full of duplicates.
**Fix:**
1. Add UNIQUE constraint to events table: `UNIQUE(source, event_type, title, timestamp)` with `ON CONFLICT REPLACE`
2. Add migration logic in `_ensure_tables()` to rebuild table with constraint
3. Add deduplication in `store_events_in_db()` — check existing before insert
4. Clean up existing duplicates with SQL: `DELETE FROM events WHERE rowid NOT IN (SELECT MIN(rowid) FROM events GROUP BY source, event_type, title, timestamp)`

### 0.4 Double-Encoded JSON in Proposals
**Bug:** conversation_extractor.py L196 calls `json.dumps({...})` creating a string, then `db.insert_proposal()` calls `json.dumps(action_data)` on it again → `"{\"source\": ...}"` double-encoded.
**Fix:** Pass the dict directly, not `json.dumps()`, from conversation_extractor to insert_proposal.

### 0.5 Knowledge Query Endpoint Crashes
**Bug:** api_server.py accesses `result.answer`, `result.confidence`, `result.sources` but `KnowledgeAnswer` has `summary` and `references` (no `confidence` or `sources`).
**Fix:** Change to `result.summary`, remove `confidence`, use `result.references` instead of `sources`.

---

## Phase 1: SECURITY — Wire the Defense Modules
**Priority:** High — security gaps before any public exposure
**Estimated effort:** 1.5 days
**Files:** api_server.py, daemon.py, approval.py, prompt_injection.py

### 1.1 Wire Prompt Injection Defense
**Status:** 301 lines of working code, tested, never imported.
**What to do:**
1. Import `PromptInjectionDefense` in api_server.py
2. Create a singleton instance in `create_api_server()`
3. Sanitize ALL external content before feeding to LLM:
   - `sanitize_email()` on Gmail content in email triage/drafting
   - `sanitize_calendar()` on calendar event descriptions
   - `sanitize_message()` on Telegram messages
   - General `check_content()` on chat context from memory search results
4. Apply in conversation_extractor.py before sending chat content to extraction LLM
5. Apply in briefing.py `_llm_format()` before narrative generation
6. Log all threat detections at WARNING level

### 1.2 Wire Approval Gate
**Status:** 431 lines of working code, tested, never instantiated.
**What to do:**
1. Instantiate `ApprovalGate` in `create_api_server()` with proper DB backend
2. Pass to `SkillRuntime` (currently receives `approval_gate=None`)
3. Wire `POST /proposals/{id}/approve` to actually execute the approved action via `ApprovalGate.execute_approved()`
4. Register `draft_email_tool()` and `send_approved_email_tool()` as agent tools
5. Wire `POST /proposals/{id}/reject` to record rejection reason
6. Add WebSocket notification when proposal needs approval

### 1.3 Add CORS Middleware
**Bug:** No CORS headers. Frontend at :3000 talks to API at :7432 — browsers block this.
**Fix:** Add `CORSMiddleware` to FastAPI app with:
- `allow_origins=["http://localhost:3000"]` (configurable)
- `allow_methods=["*"]`
- `allow_headers=["*"]`
- `allow_credentials=True`

### 1.4 WebSocket Authentication
**Bug:** WebSocket endpoint has no auth check.
**Fix:** Add `verify_api_key` check in WebSocket handshake. Reject unauthenticated connections.

### 1.5 Fix Default Empty Auth Token
**Bug:** `auth_token=""` means all endpoints are unauthenticated by default.
**Fix:**
1. Generate a random auth token on first run if none configured
2. Print token to stdout on startup
3. Store in config file for subsequent runs
4. Frontend reads from next.config.ts rewrite (existing pattern works)

### 1.6 Add Rate Limiting
**Fix:** Add `slowapi` rate limiting middleware:
- Chat endpoint: 30 req/min
- Other endpoints: 60 req/min
- WebSocket: connection limit per IP

---

## Phase 2: ARCHITECTURE — Clean Up Resource Lifecycle
**Priority:** High — prevents resource waste, split state, and bugs
**Estimated effort:** 1 day
**Files:** daemon.py, api_server.py

### 2.1 Shared Resource Container
**Bug:** MemoryManager created 3x, LLMRouter 3x, BriefingGenerator 2x, PatternDetector 2x, KnowledgeGraph 2x in daemon.py
**Fix:** Create a `ResourceContainer` dataclass shared across all daemon subsystems:
```python
@dataclass
class ResourceContainer:
    db: OmniBrainDB
    memory: MemoryManager
    router: LLMRouter
    briefing: BriefingGenerator
    knowledge: KnowledgeGraph
    patterns: PatternDetector
    review: ReviewEngine
    approval: ApprovalGate
    injection: PromptInjectionDefense
```
1. Create ALL resources once in `OmniBrainDaemon.run()`
2. Pass container to `_api_server()`, `_proactive_loop()`, `_skill_runtime_loop()`
3. Each subsystem extracts what it needs from the container
4. Single DB connection, single MemoryManager, single LLMRouter

### 2.2 Fix Deprecated asyncio Usage
**Bug:** Multiple uses of `asyncio.get_event_loop().create_task()` — deprecated since Python 3.10.
**Fix:** Replace all with `asyncio.get_running_loop().create_task()` or `asyncio.create_task()`.

### 2.3 Fix f-string SQL
**Bug:** `prune_old_data()` and `get_observations()` use f-strings in SQL queries.
**Fix:** Replace with parameterized queries. For `datetime('now', '-? days')`, use two-step approach: compute the cutoff date in Python, pass as parameter.

### 2.4 Fix ContactInfo TypeError
**Bug:** Onboarding passes `ContactInfo(source="gmail")` but ContactInfo dataclass has no `source` field.
**Fix:** Either add `source` field to ContactInfo or remove the kwarg from onboarding.

### 2.5 Add UNIQUE Constraint on Briefings
**Bug:** Multiple briefings can be stored for the same date+type.
**Fix:** Add `UNIQUE(type, date(generated_at))` constraint to briefings table.

---

## Phase 3: WIRE DEAD CODE — Or Remove It
**Priority:** Medium-high — 1,172 lines of tested code sitting unused
**Estimated effort:** 1.5 days

### 3.1 Wire Context Resurrection (440 LOC)
**Manifesto promise:** "Magic Moment #3 — Opening an abandoned project and the AI already knows where you left off."
**What to do:**
1. Import `ContextTracker` in daemon.py
2. Hook into proactive engine as a scheduled task (check for dormant projects every 4 hours)
3. Add API endpoint: `GET /api/v1/context/resurrection` — returns context summary for current project
4. Add proactive notification: "You haven't touched Project X in 2 weeks. Here's where you left off..."
5. Wire into chat context: when user mentions a project, inject resurrection summary

### 3.2 Ensure Prompt Injection is Fully Active (Phase 1.1)
Already covered in Phase 1.1 — just ensuring no dead code remains.

### 3.3 Ensure Approval Gate is Fully Active (Phase 1.2)
Already covered in Phase 1.2 — just ensuring no dead code remains.

---

## Phase 4: FRONTEND CRITICAL FIXES
**Priority:** High — visible bugs that break user experience
**Estimated effort:** 2 days
**Files:** chat.tsx, briefing.tsx, home.tsx, api.ts, store.ts, app-shell.tsx, globals.css

### 4.1 Fix Chat Action Buttons (Dead onClick)
**Bug:** chat.tsx L78-85 — action buttons render but have no onClick handler. `ChatAction` has `type` and `data` but they're unused.
**Fix:**
1. Implement `handleAction(action: ChatAction)` dispatcher:
   - `type: "navigate"` → `useNavigate(action.data.view)`
   - `type: "approve"` → `api.approveProposal(action.data.id)`
   - `type: "draft"` → `api.sendChat(action.data.prompt)` (re-sends as user message)
   - `type: "link"` → `window.open(action.data.url)`
2. Wire onClick to each action button
3. Add visual feedback (loading state while action executes)

### 4.2 Fix Snooze Button (Dead in both briefing.tsx and home.tsx)
**Bug:** Snooze buttons render but have no onClick handler. No API endpoint exists.
**Fix:**
1. Add `POST /api/v1/proposals/{id}/snooze` backend endpoint — sets `status="snoozed"` with `snooze_until` timestamp
2. Add `snoozeProposal(id: string, hours: number)` to api.ts
3. Wire Snooze button: show a small duration picker (1h, 4h, tomorrow) then call API
4. Snoozed proposals reappear after the snooze period via proactive engine

### 4.3 Fix Chat Input — Change to Textarea
**Bug:** Single-line `<input>` can't handle multi-line messages.
**Fix:**
1. Replace `<input>` with `<textarea>` + auto-resize
2. Enter submits, Shift+Enter adds newline
3. Max height of ~200px with scroll for very long messages
4. Keep auto-focus behavior

### 4.4 Fix Chat Error Handling
**Bug:** Error message appended to partial streamed content ("Here's what I foSomething went wrong").
**Fix:**
1. On error, replace the entire last assistant message (not append)
2. Add a "Retry" button to the error message
3. Store the failed user message so retry re-sends it

### 4.5 Fix streamChat — Add Timeout and Buffer Flush
**Bug:** No timeout, no retry, remaining buffer silently dropped.
**Fix:**
1. Add `AbortController` with 120s timeout
2. After stream ends, process remaining buffer
3. On timeout, show "Response took too long. Retry?"

### 4.6 Fix Refresh Button Spin
**Bug:** briefing.tsx L352-353 — `animate-spin` on entire Button, not just icon.
**Fix:** Move `animate-spin` to the `<RefreshCw>` icon only: `<RefreshCw className={briefingLoading ? "animate-spin" : ""} />`.

### 4.7 Fix Stats Card Icons (home.tsx)
**Bug:** Events uses Zap, Contacts uses Mail — semantically wrong.
**Fix:** Events → Calendar, Contacts → Users, Proposals → ClipboardCheck, Skills → Puzzle.

### 4.8 Fix Memory Highlights Visibility (home.tsx)
**Bug:** Memory highlights hidden whenever any email/calendar/proposal data exists (wrong gating condition).
**Fix:** Always show memory highlights when they exist, as a separate section below the stats.

### 4.9 Fix Theme Flash on Load
**Bug:** HTML starts with `data-theme="dark"`, then switches after hydration if user prefers light.
**Fix:** Inline script in `<head>` that reads localStorage and sets `data-theme` before React hydrates:
```html
<script>
  (function() {
    var t = localStorage.getItem('omnibrain-theme');
    if (t) document.documentElement.setAttribute('data-theme', t);
  })();
</script>
```

### 4.10 Fix Sidebar Flash on Mobile
**Bug:** `sidebarOpen: true` default causes sidebar to flash open on mobile.
**Fix:** Default to `sidebarOpen: false` on mobile (check `window.innerWidth < 640`), `true` on desktop. Persist preference in localStorage.

### 4.11 Fix Missing Geist Font
**Bug:** Geist referenced but never imported.
**Fix:** Add `next/font/google` import for Geist in layout.tsx, apply to body.

### 4.12 Fix Card Animation on Re-render
**Bug:** Every card applies `slide-up` animation on every render.
**Fix:** Only animate on mount using `useRef` or CSS `animation-fill-mode: forwards` with a flag.

### 4.13 Fix Settings Navigation from User Menu
**Bug:** top-bar.tsx — Settings uses direct store mutation, doesn't update URL.
**Fix:** Use `useNavigate("settings")` instead of `useStore.getState().setView("settings")`.

---

## Phase 5: MISSING FRONTEND VIEWS
**Priority:** Medium — manifesto promises these screens
**Estimated effort:** 3 days

### 5.1 Session Management UI for Chat
**What:** Users can't start new chats, see history, or switch sessions.
**Existing:** `api.getChatSessions()` and `api.deleteChatSession()` exist but are never used.
**Build:**
1. "New Chat" button in chat view header
2. Session list sidebar/drawer showing past conversations with timestamps
3. Click a session to load its history
4. Delete sessions with confirmation
5. Auto-title sessions based on first user message

### 5.2 Timeline View
**Manifesto:** "Timeline — Visual log of everything observed and done. Filterable."
**Build:**
1. New component: `web/components/views/timeline.tsx`
2. Vertical timeline with date separators
3. Each entry shows: timestamp, event type icon, title, source badge
4. Filters: by source (gmail, calendar, chat, skill), by date range, by type (event, contact, proposal, observation)
5. API endpoint: `GET /api/v1/timeline` — returns unified stream of all events, proposals, observations ordered by timestamp
6. Infinite scroll with pagination
7. Add route: `/timeline`

### 5.3 Contacts View
**Manifesto implies:** "12 important contacts identified" — users should be able to browse these.
**Build:**
1. New component: `web/components/views/contacts.tsx`
2. Grid/list of contacts with: name, email, last contact date, interaction count, importance score
3. Contact detail page: interaction history, relationship notes, knowledge graph for this person
4. API endpoint already exists: `GET /api/v1/knowledge/contacts` (needs to be added if not present)
5. Search/filter by name
6. Add route: `/contacts`

### 5.4 Knowledge Graph Explorer
**Manifesto:** Knowledge Graph is a core differentiator but has no UI.
**Build:**
1. New component: `web/components/views/knowledge.tsx`
2. Natural language query input: "What did Marco say about pricing?"
3. Results displayed as cards with quotes, dates, sources
4. Optional: simple relationship visualization (contacts ↔ topics)
5. Uses existing `GET /api/v1/knowledge/query` endpoint (after Phase 0.5 fix)
6. Add route: `/knowledge`

### 5.5 Persistent Chat Input Across Views
**Manifesto layout:** "Ask me anything" at bottom of every screen, not just chat.
**Build:**
1. Move chat input to AppShell (appears on all views)
2. On non-chat views: compact single-line input that expands on focus
3. Typing and pressing Enter navigates to chat view with the message pre-sent
4. Keyboard shortcut `/` focuses the global input (already partially implemented via useHotkeys)

---

## Phase 6: FRONTEND UX POLISH
**Priority:** Medium — differentiates "decent product" from "people go crazy for this"
**Estimated effort:** 2 days

### 6.1 Add Error States to All Views
**Manifesto:** "Error states are recoverable (never dead ends)"
**Build:** Each view gets an error component with:
- Clear error message (not technical jargon)
- "Try Again" button
- "Report Issue" link (optional)

### 6.2 Add Offline Detection
**Build:**
1. `useOnlineStatus()` hook using `navigator.onLine` + `online`/`offline` events
2. Global banner at top: "You're offline. Reconnect to sync."
3. Suppress individual error toasts when offline
4. Auto-refresh data when back online

### 6.3 Add Missing Micro-Animations
**Manifesto:** "Approval actions have micro-animations (checkmark draws itself)"
**Build:**
1. Approve button → animated checkmark (CSS `draw-check` keyframe already exists, just needs to be wired)
2. Reject button → fade-to-red with shake
3. Install skill → progress indicator → success bounce
4. Copy button in chat → checkmark icon swap for 2s
5. Chat typing indicator → already exists, verify it's smooth

### 6.4 Replace AppShell Spinner with Skeleton
**Manifesto:** "Skeleton UI for loading (never spinners)"
**Fix:** Replace the loading state in app-shell.tsx L128-131 with a full-page skeleton matching the shell layout.

### 6.5 Add "Last Updated" Timestamps
**Build:** Show "Updated 5 minutes ago" on briefing and home data sections. Helps users trust data freshness.

### 6.6 Add Pull-to-Refresh for Briefing
**Build:** PWA-style pull gesture on mobile that triggers briefing refresh.

### 6.7 Add Message Timestamps in Chat
**Bug:** `ChatMessage.timestamp` is set but never rendered.
**Fix:** Show timestamps on messages (hover or always, grouped by time window).

### 6.8 Add Copy Feedback in Chat
**Bug:** Copy button shows no feedback.
**Fix:** Swap icon from Copy → Check for 2 seconds after successful copy.

### 6.9 WebSocket Connection Status
**Build:** Small dot indicator in TopBar:
- Green = connected
- Yellow = reconnecting
- Red = disconnected

### 6.10 Toast Position on Mobile
**Bug:** Fixed bottom-right toasts overlap chat input on mobile.
**Fix:** On mobile (`sm:` breakpoint), move toasts to top-center.

### 6.11 Notification Panel Overflow on Mobile
**Bug:** `w-[380px]` overflows on screens < 400px.
**Fix:** Add `max-w-[90vw]` to notification panel.

### 6.12 Add 404, Error, and Loading Pages
**Build:**
1. `app/not-found.tsx` — branded 404 with search and home link
2. `app/error.tsx` — global error boundary with retry
3. `app/loading.tsx` — skeleton loading state

---

## Phase 7: BACKEND COMPLETENESS
**Priority:** Medium — features that make the product feel "complete"
**Estimated effort:** 2 days

### 7.1 Add Snooze API Endpoint
**Build:** `POST /api/v1/proposals/{id}/snooze` with `snooze_until` datetime.
- Add `snoozed_until` column to proposals table
- Proactive engine checks for due snoozed proposals and resurfaces them

### 7.2 Timeline API Endpoint
**Build:** `GET /api/v1/timeline?since=&until=&source=&limit=&offset=`
- Unified query across events, proposals, observations, briefings
- Ordered by timestamp descending
- Support pagination via offset/limit

### 7.3 Contacts API Endpoints
**Build:**
- `GET /api/v1/contacts` — list all with importance scores
- `GET /api/v1/contacts/{email}` — detail with interaction history
- `GET /api/v1/contacts/{email}/graph` — knowledge graph relationships

### 7.4 Chat Session Management
**Build:**
- `POST /api/v1/chat/sessions/new` — create new session
- Auto-title sessions from first message (LLM or first N words)
- Ensure `GET /api/v1/chat/sessions` returns sorted list with titles

### 7.5 Fix Memory Search OR → AND
**Bug:** FTS5 query sanitizer converts "meeting Marco" to `"meeting" OR "Marco"`.
**Fix:** Change default join from OR to AND for precision.

### 7.6 Data Freshness Headers
**Build:** Add `X-Data-Generated-At` header to briefing and stats responses so frontend can show "last updated" time.

### 7.7 Fix Proactive Engine Field Name Bugs
**Bug:** `_evening_summary()` and `_weekly_review()` use `briefing_type=` but field is `type=`.
**Fix:** Correct field names in both functions.

### 7.8 Fix Proactive Engine Calendar Date Filter
**Bug:** `_check_calendar()` fetches ALL events (no date filter) every cycle.
**Fix:** Pass `since=datetime.now()` to only process future/today events.

### 7.9 Fix Weekly Task should_run Logic
**Bug:** Checks `(now - self.last_run).days < 6` — won't detect week boundaries correctly.
**Fix:** Check `self.last_run.isocalendar()[1] != now.isocalendar()[1]` (different ISO week number).

---

## Phase 8: TEST COVERAGE
**Priority:** Medium — prevents regression as we build
**Estimated effort:** 1.5 days

### 8.1 Test conversation_extractor.py (0 tests!)
**Build:**
- Test extraction with mock LLM response
- Test persistence of events, contacts, preferences, proposals
- Test error handling (malformed LLM output, DB errors)
- Test deduplication
- Test all-day event detection
- ~15 test cases

### 8.2 Test Narrative Briefing
**Build:**
- Test `generate_narrative()` with mock router
- Test `generate_and_store_narrative()` stores to DB
- Test `_llm_format()` output quality
- Test fallback when LLM fails
- ~8 test cases

### 8.3 Test Date-Filtered Briefing
**Build:**
- Test `_collect_calendar()` only returns today's events
- Test `_collect_emails()` only returns last 24h
- Test all-day event rendering
- ~6 test cases

### 8.4 Test Approval Gate Wiring
**Build:**
- Test approve endpoint executes action
- Test reject endpoint records reason
- Test snooze endpoint sets timer
- ~5 test cases

### 8.5 Test Prompt Injection Integration
**Build:**
- Test that email content is sanitized before LLM
- Test that high-threat content is blocked
- Test that clean content passes through
- ~5 test cases

### 8.6 Test Timeline API
**Build:**
- Test unified query across entity types
- Test pagination
- Test source filtering
- ~5 test cases

### 8.7 E2E Tests
**Build:**
- Test full onboarding → briefing flow
- Test chat → extraction → briefing cycle
- Test proposal lifecycle (create → approve/reject → execute)
- ~5 test scenarios

---

## Phase 9: PRODUCTION READINESS
**Priority:** Pre-launch — required for public deployment
**Estimated effort:** 2 days

### 9.1 GDPR Compliance Verification
- Verify `export_all()` exports EVERYTHING (including memory.db)
- Verify `wipe_all()` wipes EVERYTHING
- Add UI button in Settings for both operations
- Add confirmation dialogs with clear warnings
- Test that wipe actually removes all data (no orphaned files)

### 9.2 EU AI Act Compliance
- Ensure all AI-generated content is clearly marked
- Email drafts include: "Drafted by OmniBrain AI on behalf of [User]"
- No consciousness claims anywhere in the product
- Add disclosure in Settings/About

### 9.3 Performance Audit
- Profile briefing generation time (target: < 3s)
- Profile chat response time (target: first token < 1s)
- Profile API response times for all endpoints
- Optimize slow spots (batch DB queries, reduce LLM calls)
- Add `X-Response-Time` header to all API responses

### 9.4 Monitoring & Health
- `GET /api/v1/health` endpoint (already exists — verify it checks DB, LLM, memory)
- Structured logging throughout (JSON format, rotation)
- Error reporting with context (not just stack traces)
- Dashboard: LLM costs, API latency, error rate

### 9.5 Database Maintenance
- Implement proper data retention per manifesto (events: 1yr, proposals: 90d, sessions: 30d)
- Ensure `prune_old_data()` runs on schedule
- Add DB backup command/schedule
- Add DB migration system for schema changes

### 9.6 PWA Enhancement
- Verify manifest.json is complete (icons, theme color, display: standalone)
- Add service worker for offline caching of static assets
- Consider push notification support (Web Push API)

### 9.7 Documentation
- README: clear setup instructions (1-command install)
- CONTRIBUTING.md: how to contribute Skills
- Skill Protocol docs: "Build a Skill in 30 minutes"
- API documentation via OpenAPI/Swagger (FastAPI auto-generates)

---

## Phase 10: THE MAGIC POLISH
**Priority:** Pre-launch — this is what makes people share and say "WTF"
**Estimated effort:** 2 days

### 10.1 Shareable Briefing Snapshot
**Build:** "Share this briefing" button that generates a beautiful screenshot-like card (no sensitive data) for sharing on X/social.

### 10.2 Onboarding "WTF" Animation Sequence
**Fix:** The missing `tailwindcss-animate` plugin means onboarding animations don't work.
**Build:**
1. Install `tailwindcss-animate` plugin OR implement the needed keyframes in globals.css
2. Staggered reveal of insight cards (0.2s delay between each)
3. Counter animation for "247 emails analyzed" (count up from 0)
4. Subtle particle/confetti on the reveal moment

### 10.3 First-Run Guided Tour
**Build:** Brief 4-step tooltip tour for first-time users:
1. "This is your briefing — check it every morning"
2. "Chat with me about anything"
3. "Install Skills to teach me new abilities"
4. "I'll learn your patterns and become more useful over time"

### 10.4 Smart Suggestions in Chat
**Build:** Dynamic suggestion chips above chat input that change based on context:
- Morning: "Show me my briefing", "What's on my calendar?"
- After receiving email: "Draft a reply to Marco"
- After pattern detection: "Tell me about my patterns"

### 10.5 Briefing Narrative Mode
**Build:** Toggle between "Cards view" (current) and "Narrative view" (the LLM-generated story).
The narrative is a friendly, personal summary like:
> "Good morning Francesco. You have a busy day ahead — 3 meetings starting at 10:00. Marco still hasn't replied to that pricing email from 5 days ago. I noticed you've been spending 40% more on software subscriptions this month..."

### 10.6 Proactive Feed as Sidebar
**Manifesto layout:** Shows proactive feed as left sidebar, but current implementation uses navigation sidebar.
**Build:**
1. On desktop (lg+), split layout: left = proactive feed, right = main content
2. Proactive feed shows: pending proposals, pattern alerts, follow-up reminders
3. On mobile: proactive feed accessible via swipe or bottom tab

---

## Execution Order & Dependencies

```
Week 1: Foundation
├── Phase 0 (Day 1)          — Fix visible bugs
├── Phase 1 (Day 2-3)        — Security hardening
└── Phase 2 (Day 3-4)        — Architecture cleanup

Week 2: Features
├── Phase 3 (Day 5)          — Wire dead code
├── Phase 4 (Day 5-7)        — Frontend critical fixes
└── Phase 5 (Day 7-9)        — Missing views

Week 3: Polish & Ship
├── Phase 6 (Day 10-11)      — UX polish
├── Phase 7 (Day 11-12)      — Backend completeness
├── Phase 8 (Day 13-14)      — Test coverage
├── Phase 9 (Day 15-16)      — Production readiness
└── Phase 10 (Day 17-18)     — Magic polish

Day 19: Private beta (20-50 users)
Day 20: Bug fixes from beta feedback
Day 21: PUBLIC LAUNCH
```

---

## Dependency Graph

```
Phase 0 ──→ Phase 4.2 (briefing frontend needs backend date filter)
Phase 1.1 ──→ Phase 3.2 (prompt injection must be wired before declaring live)
Phase 1.2 ──→ Phase 3.3 (approval gate must be wired before declaring live)
Phase 1.2 ──→ Phase 4.2 (snooze needs approval gate for action execution)
Phase 2.1 ──→ Phase 3.1 (context resurrection needs shared resources)
Phase 0.5 ──→ Phase 5.4 (knowledge explorer needs working API)
Phase 5.2 ──→ Phase 7.2 (timeline view needs timeline API)
Phase 5.3 ──→ Phase 7.3 (contacts view needs contacts API)
Phase 5.1 ──→ Phase 7.4 (session UI needs session management API)
Phase 4.2 ──→ Phase 7.1 (snooze button needs snooze API)
Phase 7 ──→ Phase 8   (test new endpoints after building them)
```

---

## Success Criteria

When ALL phases are complete:

- [ ] **Zero dead code** — every module is imported and used
- [ ] **Zero broken endpoints** — all API endpoints return valid data
- [ ] **Zero dead buttons** — every button has a handler
- [ ] **Every manifesto screen exists** — Home, Chat, Briefing, Skills, Settings, Timeline, Contacts, Knowledge
- [ ] **Security is active** — prompt injection defense on all external content, approval gate on all actions
- [ ] **Events are deduplicated** — no duplicate calendar events or emails
- [ ] **Briefing shows today only** — no all-time data
- [ ] **All-day events say "All day"** — not "00:00"
- [ ] **Tests pass** — 1500+ with new tests, zero failures
- [ ] **Frontend builds clean** — zero TypeScript errors
- [ ] **Manifesto compliance** — every promise delivered
- [ ] **GDPR compliant** — export + wipe work perfectly
- [ ] **< 30 seconds to first insight** — onboarding is fast and magical
- [ ] **Morning briefing is a daily habit** — beautiful, useful, personal

---

## Metrics to Track During Development

| Metric | Current | Target |
|---|---|---|
| Tests passing | 1,474 | 1,600+ |
| Dead code lines | ~1,172 | 0 |
| Dead buttons | 4 | 0 |
| Broken endpoints | 1 (knowledge query) | 0 |
| Security gaps | 4 (no CORS, no WS auth, no prompt injection, no approval) | 0 |
| Manifesto screens | 6/10 | 10/10 |
| Frontend bugs | 13 | 0 |
| Backend bugs | 15 | 0 |

---

*This plan is the bridge between where OmniBrain is and what the manifesto promises. Every phase advances toward one goal: a product so good that users can't imagine life without it.*

*— Generated 18 February 2026*
