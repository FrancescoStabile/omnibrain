# Architecture — Quick Reference

> This file is a summary. For the full platform architecture, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

---

## System Overview

OmniBrain is an **open-source AI platform** with three layers:

1. **Web UI** — Next.js 15 + shadcn/ui. Chat, proactive feed, Skill Store, settings.
2. **API Layer** — FastAPI + WebSocket. REST endpoints + real-time notifications.
3. **The Brain** — Python core. Agent engine, memory, proactive engine, Skill Runtime, LLM router, approval gate.

Single Python process, multiple asyncio tasks. SQLite + FTS5 for all persistence. No external dependencies (no Redis, no PostgreSQL, no Docker required).

## Key Components

| Component | Source | Purpose |
|-----------|--------|---------|
| Agent Engine | `src/omnigent/agent.py` | ReAct loop, reasoning graph, planner |
| LLM Router | `src/omnigent/router.py` | DeepSeek, Claude, OpenAI, Ollama |
| Memory | `src/omnibrain/memory.py` | SQLite FTS5 + optional ChromaDB |
| Knowledge Graph | `src/omnibrain/knowledge_graph.py` | Entity-relationship queries |
| Proactive Engine | `src/omnibrain/proactive/` | Patterns, scorer, proposer, briefings |
| Approval Gate | `src/omnibrain/approval.py` | 3-level action approval |
| Skill Runtime | `src/omnibrain/skill_runtime.py` | Load, sandbox, trigger Skills |
| API Server | `src/omnibrain/interfaces/api_server.py` | FastAPI + WebSocket |
| Web UI | `web/` | Next.js frontend |

## Technology Decisions

- **Python** — AI ecosystem, 10K+ lines written, 983 tests passing
- **SQLite + FTS5** — Zero setup, local-first, GDPR-friendly
- **FastAPI** — Native async, WebSocket, OpenAPI docs
- **Next.js + shadcn/ui** — Beautiful defaults, Tailwind, accessible
- **Single process** — SQLite works best with single writer, no IPC complexity

## Deep Dive

- [Full Architecture](docs/ARCHITECTURE.md) — Process model, communication patterns, deployment
- [API Specification](docs/API-SPEC.md) — Every REST + WebSocket endpoint
- [Data Models](docs/DATA-MODELS.md) — SQLite schemas
- [Security Model](docs/SECURITY.md) — Sandboxing, prompt injection defense
- [Skill Protocol](docs/SKILL-PROTOCOL.md) — How Skills work
