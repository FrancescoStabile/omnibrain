# Changelog

All notable changes to OmniBrain will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Platform Pivot (February 16, 2026)

OmniBrain is now an **open-source AI platform** with Skill Protocol, Web UI, and marketplace.

#### Changed (docs)
- **manifesto.md** — Complete rewrite (v2.0). Platform vision, Skill Protocol, addiction loop, 21-day sprint.
- **README.md** — Complete rewrite. Platform-first presentation, Skill examples, new architecture diagram.
- **ARCHITECTURE.md** — Rewritten as quick reference pointing to full `docs/ARCHITECTURE.md`.
- **CONTRIBUTING.md** — Rewritten for platform contribution model (Skills, Web UI, core engine).
- **CLAUDE.md** — Updated for platform pivot, new docs structure, 21-day sprint.

#### Added (docs)
- `docs/INDEX.md` — Documentation hub
- `docs/VISION.md` — Product vision, target users, impact
- `docs/DIFFERENTIATION.md` — Competitive analysis (vs OpenClaw, ChatGPT, Rewind, Siri)
- `docs/SKILL-PROTOCOL.md` — Complete Skill Protocol specification
- `docs/ARCHITECTURE.md` — Full platform architecture
- `docs/API-SPEC.md` — REST + WebSocket API specification
- `docs/DATA-MODELS.md` — SQLite schemas for platform
- `docs/UX-BIBLE.md` — Design system (color, typography, components, animations)
- `docs/SECURITY.md` — Security model, Skill sandboxing
- `docs/LEGAL.md` — GDPR, EU AI Act, API terms
- `docs/DEVELOPMENT-GUIDE.md` — Dev setup, conventions, testing
- `docs/COMMUNITY-STRATEGY.md` — Community building strategy
- `docs/LAUNCH-PLAYBOOK.md` — 21-day sprint plan
- `docs/BUSINESS-MODEL.md` — Revenue model (Obsidian model)

#### Removed (docs)
- All legacy phase docs: `docs/PHASE-0.md` through `docs/PHASE-6-SCALE.md`
- `docs/ROADMAP.md`, `docs/BUILD-IN-PUBLIC.md`, `docs/DECISION-FRAMEWORK.md`
- `docs/LLM-STRATEGY.md`, `docs/METRICS.md`, `docs/TOOLS-SPEC.md`

#### Added (scaffolding)
- `skills/` directory with 5 built-in Skill stubs (email-manager, calendar-assistant, morning-briefing, memory-search, pattern-detector)
- `web/` directory placeholder for Next.js frontend

### Foundation (pre-pivot, 983 tests passing)

Everything below was built before the platform pivot and serves as the core engine:

#### Core Engine (Omnigent)
- **Agent Loop** — Full ReAct with streaming, circuit breaker, loop detection, adaptive timeouts
- **LLM Router** — DeepSeek, Claude, OpenAI, Ollama with auto-fallback and cost tracking
- **Reasoning Graph** — Directed graph with node states, edge activation, fuzzy capability matching
- **Hierarchical Planner** — TaskPlan → TaskPhase → TaskStep with LLM refinement
- **Smart Context** — 3-level trimming + semantic compression
- **Plugin System** — Discovery, loading, checksum verification → base for Skill Protocol
- **Session Persistence** — Checkpoint/replay, multi-format export
- **Cost Tracker** — Per-provider token/cost tracking with budget limits

#### Domain Layer (OmniBrain)
- **Memory** — SQLite FTS5 + optional ChromaDB dual-backend
- **Knowledge Graph** — who_said_what, correlate, contact_graph, topic_timeline
- **Briefing Engine** — Morning/evening/weekly, works without LLM
- **Approval Gate** — PRE_APPROVED / NEEDS_APPROVAL / NEVER levels
- **Prompt Injection Guard** — 16+ pattern sanitizer
- **Gmail Integration** — Fetch, search, classify, draft, triage
- **Calendar Integration** — Events, meeting briefs, conflict detection
- **Proactive Engine** — 6 scheduled tasks, pattern detection, priority scoring
- **Context Resurrection** — Resume abandoned projects with full context
- **Review Engine** — Evening/weekly retrospectives
- **API Server** — FastAPI with 11 endpoints (foundation)
- **Telegram Bot** — 9 commands with inline keyboards
- **CLI** — 15 subcommands for all operations
