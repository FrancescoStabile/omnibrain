# OmniBrain — Architecture

> Technical architecture of OmniBrain and the Omnigent framework that powers it.
> For the complete vision, see [manifesto.md](manifesto.md).
> For usage and quick start, see [README.md](README.md).

---

## Table of Contents

- [Design Philosophy](#design-philosophy)
- [OmniBrain System Overview](#omnibrain-system-overview)
- [How Omnigent Powers OmniBrain](#how-omnigent-powers-omnibrain)
- [The Agent Loop (ReAct)](#the-agent-loop-react)
- [LLM Router](#llm-router)
- [Reasoning Graph](#reasoning-graph)
- [Hierarchical Planner](#hierarchical-planner)
- [Context Management](#context-management)
- [Domain Profile & State](#domain-profile--state)
- [Post-Processing Pipeline](#post-processing-pipeline)
- [Tool System](#tool-system)
- [Plugin Architecture](#plugin-architecture)
- [Session Persistence](#session-persistence)
- [The Proactive Engine](#the-proactive-engine)
- [Memory Architecture](#memory-architecture)
- [Security Model](#security-model)
- [Extension Model](#extension-model)
- [Design Decisions](#design-decisions)

---

## Design Philosophy

OmniBrain is built on six principles:

1. **Local-first.** All data stored on the user's machine. Zero cloud by default. No telemetry. No phone-home.

2. **Proactive, not reactive.** OmniBrain doesn't wait for commands — it observes, reasons, and proposes actions continuously.

3. **Never act without approval.** OmniBrain proposes. The human decides. All outgoing actions (emails, messages, modifications) require explicit user approval.

4. **Domain-agnostic core, domain-specific extensions.** Omnigent (the brain) is a pure agent framework. OmniBrain extends it with personal AI domain logic via registries and subclass hooks.

5. **Never crash.** Every extension point wraps execution in try/except. A bad extractor or malformed API response must never stop the daemon.

6. **Ship something real every week.** Not planned. Not designed. Shipped. Working code that a human can use.

---

## OmniBrain System Overview

OmniBrain runs as a **persistent daemon** (systemd on Linux, launchd on macOS) with multiple concurrent asyncio tasks:

```
omnibrain-daemon (main process)
├── collector_loop      — polls Gmail, Calendar, GitHub every N minutes
├── proactive_loop      — checks patterns, proposes actions
├── briefing_scheduler  — generates daily/weekly briefings
├── telegram_bot        — listens for user messages
├── api_server          — REST API for CLI + desktop app
└── cleanup_loop        — maintains DB, prunes old data
```

### Component Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    OMNIBRAIN DAEMON                           │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │  COLLECTOR    │  │  OMNIGENT    │  │  PROACTIVE       │   │
│  │  SERVICE      │  │  BRAIN       │  │  ENGINE          │   │
│  │              │  │              │  │                  │   │
│  │ Gmail API    │  │ Agent Loop   │  │ Pattern Detector │   │
│  │ Calendar API │  │ Reasoning    │  │ Priority Scorer  │   │
│  │ GitHub API   │  │ Graph        │  │ Action Proposer  │   │
│  │ File Watcher │  │ Planner      │  │ Scheduler        │   │
│  └──────┬───────┘  └──────┬───────┘  └────────┬─────────┘   │
│         │                 │                    │             │
│         ▼                 ▼                    ▼             │
│  ┌──────────────────────────────────────────────────────────┐│
│  │                    MEMORY LAYER                          ││
│  │  SQLite (structured) + ChromaDB (semantic) + Graph       ││
│  └──────────────────────────────────────────────────────────┘│
│  ┌──────────────────────────────────────────────────────────┐│
│  │                  INTERFACE LAYER                         ││
│  │  Telegram Bot │ CLI │ Desktop (Tauri) │ REST API         ││
│  └──────────────────────────────────────────────────────────┘│
│  ┌──────────────────────────────────────────────────────────┐│
│  │                   LLM ROUTER                             ││
│  │  DeepSeek (cheap) │ Claude (smart) │ Ollama (local)      ││
│  └──────────────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────────────┘
```

### Communication Between Components

All components communicate via:
1. **Shared SQLite database** (event queue table)
2. **Python asyncio queues** (in-process events)
3. **REST API** (for external clients: CLI, desktop app)

No message broker needed — this is a single-machine system.

---

## How Omnigent Powers OmniBrain

Omnigent is not just "used" by OmniBrain — it **is** the brain. OmniBrain extends Omnigent through three key subclasses:

### OmniBrainProfile (extends DomainProfile)
Personal context: contacts, email stats, calendar events, active projects, pending proposals, observations, learned preferences. Generates a prompt summary that tells the LLM everything OmniBrain knows about the user right now.

### OmniBrainGraph (extends ReasoningGraph)
Personal reasoning chains:
- **Email chain:** email_received → urgency_classification → context_retrieval → response_drafted
- **Meeting chain:** meeting_upcoming → context_gathered → brief_ready
- **Code chain:** issue_reported → code_analyzed → fix_proposed
- **Pattern chain:** pattern_observed → pattern_confirmed → automation_proposed
- **Financial chain:** transaction_detected → anomaly_found → saving_proposed

### OmniBrainAgent (extends Agent)
Personal agent with dynamic system prompt (injects user context), OmniBrain-specific failure detection, and observation storage on findings.

### Registry Mapping

| Omnigent Registry | OmniBrain Usage |
|---|---|
| `plan_templates` | Templates for morning briefing, email triage, meeting prep, code review |
| `chains` | Email→Response, Meeting→Brief, Issue→Fix, Pattern→Automation |
| `extractors` | Parse Gmail → ContactInfo, Calendar → events, GitHub → issues |
| `reflectors` | After email triage: "3 contacts haven't heard from you in 2 weeks" |
| `error_patterns` | Gmail auth expired → re-auth. GitHub rate limit → backoff |
| `knowledge_map` | User's knowledge files (notes, preferences, patterns) |
| `examples` | Few-shot examples for email drafting, priority classification |
| `tool_timeouts` | Gmail: 30s, GitHub: 20s, LLM draft: 60s |

---

## The Agent Loop (ReAct)

**File:** `src/omnigent/agent.py`

The core of Omnigent is a ReAct (Reason-Act-Observe) loop decomposed into **overridable step methods**.

### Iteration Cycle

1. **`_do_context_management()`** — trim if messages exceed token threshold
2. **Build dynamic system prompt** — base prompt + DomainProfile + TaskPlan + ReasoningGraph + Knowledge
3. **`_do_llm_call()`** — stream LLM response via Router
4. **Handle text tokens** — emit to UI, parse findings
5. **Rate limiting** — per-iteration and total caps
6. **Human-in-the-loop** — tools with `requires_approval` trigger callback
7. **`_do_tool_execution()`** — execute in parallel with adaptive timeouts
8. **`_do_post_tool_processing()`** — extract → reflect → error recover
9. **`_check_phase_advancement()`** — advance plan phases, generate macro-reflection
10. **`_check_termination()`** — plan complete or done indicators
11. **Checkpoint** — periodically save state for replay

### Safety Mechanisms

| Mechanism | How It Works |
|-----------|-------------|
| Loop Detection | MD5 hash of tool+args. Blocks repeated identical calls. |
| Circuit Breaker | After 3 identical LLM errors, stops entirely. |
| Rate Limiting | Per-iteration cap (20) + total cap (500). |
| Human-in-the-Loop | Approval callback for sensitive tools. |
| Adaptive Timeouts | Per-tool timeout via registry. Default: 300s. |
| Max Iterations | Hard cap (default: 50). |
| Checkpoint/Replay | Saves full state every N iterations for recovery. |

### Event System

The agent yields typed events:
- `TextEvent` — LLM text token
- `ToolStartEvent` / `ToolEndEvent` — tool execution lifecycle
- `FindingEvent` — new finding registered
- `PlanEvent` — plan created
- `PhaseCompleteEvent` — phase advanced
- `UsageEvent` — token counts
- `ErrorEvent` — error occurred
- `DoneEvent` — loop finished

---

## LLM Router

**File:** `src/omnigent/router.py`

Multi-provider LLM routing with streaming, automatic fallback, and task-based selection.

### Task-Based Routing

```
PLANNING   → Claude > DeepSeek
TOOL_USE   → DeepSeek > OpenAI
ANALYSIS   → Claude > DeepSeek
REFLECTION → DeepSeek > Local
REPORT     → Claude > OpenAI
```

### OmniBrain-Specific Routing

| Task | Provider | Model | Why |
|------|----------|-------|-----|
| Email triage (bulk) | DeepSeek | deepseek-chat | Cheapest, good enough |
| Email draft | DeepSeek | deepseek-chat | Good writing, cheap |
| Meeting brief | Claude | claude-sonnet-4 | Best reasoning |
| Morning briefing | Claude | claude-sonnet-4 | Quality matters |
| Urgency classification | Ollama | qwen2.5-coder:7b | Free, local |
| Privacy-sensitive | Ollama | qwen2.5-coder:7b | Never leaves machine |

### Monthly Cost

- Light user (50 emails/day): ~$0.50/month
- Heavy user (200 emails/day): ~$2.65/month

### Provider Architecture

New providers via `LLMProvider` ABC — no router modification needed:
```python
class LLMProvider:
    async def stream(self, client, config, messages, tools, system) -> AsyncGenerator[StreamChunk, None]:
        raise NotImplementedError
```

All calls use streaming via httpx. System prompts sent as native system messages.

---

## Reasoning Graph

**File:** `src/omnigent/reasoning_graph.py`

**The key differentiator.** When a finding is confirmed, the graph activates downstream paths. The agent chains observations into multi-step reasoning.

### Concept

```
Nodes = States         (e.g., "email_received", "email_urgent", "response_drafted")
Edges = Reasoning Steps (e.g., "classify urgency", "retrieve context", "draft response")
Paths = Named Chains    (e.g., "Email → Response", "Meeting Prep", "Issue → Fix")
```

### Node States

```
UNKNOWN   → Not yet investigated
SUSPECTED → Hypothesis
CONFIRMED → Confirmed via tools
EXPLOITED → Successfully acted upon
FAILED    → Ruled out
```

### OmniBrain Graph Example

```
email_received ──classify──▶ email_urgent ──context──▶ email_context ──draft──▶ response_drafted
meeting_upcoming ──gather──▶ meeting_context ──brief──▶ meeting_brief
issue_reported ──analyze──▶ code_analyzed ──fix──▶ fix_proposed
pattern_observed ──confirm──▶ pattern_confirmed ──automate──▶ automation_proposed
```

---

## Hierarchical Planner

**File:** `src/omnigent/planner.py`

Decomposes objectives into structured execution plans.

```
TaskPlan
├── TaskPhase: "Email Triage"
│   ├── TaskStep: "Fetch new emails" (tool_hint: fetch_emails)
│   ├── TaskStep: "Classify urgency" (tool_hint: classify_email)
│   └── TaskStep: "Draft responses" (tool_hint: draft_email)
├── TaskPhase: "Calendar Review"
│   └── TaskStep: "Prepare meeting briefs" (tool_hint: generate_meeting_brief)
└── TaskPhase: "Summary"
    └── TaskStep: "Generate briefing" (tool_hint: generate_briefing)
```

Plan generation: template matching → optional LLM refinement → fallback generic plan.

Macro-reflection at phase boundaries summarizes accomplishments and adjusts strategy.

---

## Context Management

**File:** `src/omnigent/context.py`

### 3-Level Strategy

1. **DomainProfile + TaskPlan** — always in system prompt (never trimmed)
2. **Middle messages** — tool results compressed (first 300 chars + truncation)
3. **Recent window** — last N messages kept intact

### Semantic Compression

Uses LLM to intelligently summarize old messages while preserving key facts and decisions.

### Atomic Groups

Assistant messages with tool calls and their corresponding results form atomic groups — never split.

---

## Domain Profile & State

### DomainProfile (`domain_profile.py`)
Structured memory: subject, scope, hypotheses with confidence tracking, metadata. Auto-populated by extractors, injected into every LLM call.

### State (`state.py`)
Session container: messages, findings (Pydantic-validated), profile, plan, enrichment hook.

---

## Post-Processing Pipeline

After every tool execution:

1. **Extractors** — parse tool results into structured profile data
2. **Reflection** — generate strategic insight (sync or async) for LLM guidance
3. **Error Recovery** — pattern-match failures against known recovery strategies

---

## Tool System

**File:** `src/omnigent/tools/__init__.py`

### OmniBrain Tool Categories

| Category | Tools | Phase |
|----------|-------|-------|
| Email | fetch_emails, classify_email, draft_email, send_email | 1 |
| Calendar | get_today_events, get_upcoming_events, generate_meeting_brief | 1 |
| Memory | search_memory, store_observation | 1 |
| Actions | propose_action, notify_user | 1 |
| GitHub | get_notifications, analyze_issue, review_pr, propose_fix | 2 |

### The Approval Gate

```python
PRE_APPROVED = {"fetch_emails", "get_today_events", "search_memory",
                "store_observation", "classify_email", "notify_user",
                "generate_meeting_brief", "draft_email"}

REQUIRES_APPROVAL = {"send_email", "create_event", "post_message",
                     "execute_automation", "modify_data"}
```

OmniBrain **never** executes high-impact actions without explicit user approval. This is non-negotiable.

---

## Plugin Architecture

**File:** `src/omnigent/plugins.py`

Plugins in `~/.omnigent/plugins/` can add tools, extractors, and knowledge files. Strict checksum mode with SHA-256 verification available.

---

## Session Persistence

**File:** `src/omnigent/session.py`

Auto-save to `~/.omnigent/sessions/` as JSON. Supports resume, checkpoint/replay, and encrypted sessions.

---

## The Proactive Engine

This is what separates OmniBrain from everything else — runs independently of user requests.

### Scheduled Tasks

| Task | Frequency | Description |
|------|-----------|-------------|
| check_emails | Every 5 min | Poll Gmail, classify, propose responses |
| check_calendar | Every 15 min | Check upcoming meetings, prepare briefs |
| detect_patterns | Every hour | Analyze observations for recurring patterns |
| morning_briefing | Daily 07:00 | Comprehensive morning briefing |
| evening_summary | Daily 22:00 | End-of-day summary |
| weekly_review | Monday 08:00 | Weekly stats and insights |

### Notification Levels

```
SILENT    → Stored in memory, no notification
FYI       → Batched into next briefing
IMPORTANT → Immediate notification, non-intrusive
CRITICAL  → Immediate notification, persistent
```

---

## Memory Architecture

### Layer 1: SQLite (Structured)
- Location: `~/.omnibrain/omnibrain.db`
- Tables: events, contacts, proposals, observations, preferences, briefings, sessions
- Full-text search via FTS5

### Layer 2: ChromaDB (Semantic)
- Location: `~/.omnibrain/chroma/`
- Enables natural language queries across all stored data
- Embedding model: OpenAI text-embedding-3-small or local all-MiniLM-L6-v2
- Runs in-process

### Layer 3: Knowledge Graph (Relationships)
- Via Omnigent's ReasoningGraph + SQLite relationships
- Contact-to-contact, project-to-contact, pattern chains

### Memory Lifecycle

```
Event arrives (email, calendar, etc.)
  ├── Store in SQLite (structured, queryable)
  ├── Embed in ChromaDB (semantic search)
  ├── Extract entities → update contacts, relationships
  └── Feed to OmniBrainProfile
```

---

## Security Model

1. **Local-first** — all data on user's machine
2. **Least privilege** — minimum API scopes, read-only where possible
3. **Approval gate** — all outgoing actions require approval
4. **Encrypted at rest** — SQLCipher optional
5. **Token security** — OS keychain or `~/.omnibrain/` with 600 permissions
6. **No telemetry** — zero data collection
7. **Prompt injection defense** — email content sanitized before LLM processing

---

## Extension Model

### 1. DomainRegistry (Data-Driven)

```python
from omnigent.registry import DomainRegistry

registry = DomainRegistry(
    plan_templates={...},
    chains={...},
    extractors={...},
    reflectors={...},
    error_patterns={...},
    examples={...},
    knowledge_map={...},
    tool_timeouts={...},
)
agent = Agent(registry=registry)
```

### 2. Subclass Hooks (Object-Oriented)

| Class | Override | Purpose |
|-------|----------|---------|
| `Agent` | `_is_failure()` | Domain-specific failure detection |
| `Agent` | `_build_dynamic_system_prompt()` | Extra context sections |
| `Agent` | `_on_finding()` | Finding post-processing |
| `ReasoningGraph` | `_build_default_graph()` | Domain reasoning chains |
| `DomainProfile` | `to_prompt_summary()` | Custom LLM context |
| `LLMProvider` | `stream()` | Add new LLM providers |

---

## Design Decisions

### Why Python (not Rust) for the Daemon?
1. Omnigent is Python — rewriting = months wasted, zero user value
2. asyncio handles local daemon concurrency easily (< 50 concurrent tasks)
3. All APIs (Google, Telegram, ChromaDB) have first-class Python SDKs
4. Performance bottleneck is LLM latency (100-500ms), not language speed
5. Rust is Phase 4+ optimization IF profiling shows it's needed

### Why no message broker?
Single-machine system. SQLite + asyncio queues are sufficient and zero-config.

### Why Telegram over WhatsApp?
- Official API (no ban risk)
- Free (WhatsApp charges per message)
- Rich features (inline keyboards for approval flow)
- Better for tech-literate users (Phase 1 target)

### Why httpx instead of provider SDKs?
Direct HTTP control. No dependency weight, no version conflicts, full streaming control.

### Why no LangChain / CrewAI?
Omnigent is lower-level — it's the engine, not the car. No mandatory abstractions.

---

*For the complete specification including every schema, every tool, and every prompt, see [manifesto.md](manifesto.md).*
