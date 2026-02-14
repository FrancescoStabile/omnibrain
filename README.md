<div align="center">

# OmniBrain

**The AI that never sleeps.**

A local-first, open-source AI agent that monitors your digital life 24/7 and acts proactively on your behalf. Built on [Omnigent](https://github.com/FrancescoStabile/omnigent) — the most advanced open-source agent framework.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Build in Public](https://img.shields.io/badge/build%20in%20public-daily%20on%20X-black.svg)](https://x.com/Francesco_Sta)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

[Architecture](ARCHITECTURE.md) · [Manifesto](manifesto.md) · [Roadmap](docs/ROADMAP.md) · [Contributing](CONTRIBUTING.md)

</div>

---

> **OmniBrain is in active development.** We're building this in public, one day at a time. Follow the journey on [X/Twitter](https://x.com/Francesco_Sta). Star the repo to stay updated.

---

## What is OmniBrain?

While you sleep, OmniBrain is working.

It triages your emails. Prepares your meeting briefs. Detects spending anomalies. Finds that conversation you had 3 weeks ago. Drafts responses for urgent messages. Builds a knowledge graph of **your** life — and uses it to act on your behalf.

**OmniBrain is a persistent, proactive AI agent.** Not a chatbot. Not a memory tool. Not a task automator. It **observes, reasons, and acts** — continuously, locally, privately.

```
While you slept (23:47 → 06:30):

✓ Triaged 12 emails (3 urgent, 4 FYI, 5 archived)
✓ GitHub issue #52: analyzed codebase, found root cause in auth.py:147
  → Proposed fix ready as draft PR
✓ Investor replied at 02:14 — sentiment: positive
  → Follow-up draft prepared
✓ Subscription renewal detected: $49/mo for unused service
  → Cancellation link ready (saves $588/year)

All actions are PROPOSALS. Nothing was sent without your approval.
```

### How is this different?

| Product | Model | OmniBrain |
|---------|-------|-----------|
| ChatGPT / Claude | Reactive chat, session-based | Persistent, proactive, context-aware |
| Siri / Alexa | Voice commands, no reasoning | Reasoning Graph, multi-step chains |
| Rewind / Limitless | Passive memory capture | Active intelligence + action |
| Apple Intelligence | Cloud-first, closed, generic | Local-first, open source, personal |

**The Linux of personal AI.** Open source. Runs on your hardware. Your data never leaves your machine. No corporation can shut it down.

---

## The Magic Moments

These are the experiences that make OmniBrain worth having.

### Morning Briefing
```
OmniBrain Morning Briefing — Feb 15, 2026

Overnight analysis:
• 34 emails received → 3 require your response (drafts ready)
• Meeting at 14:00 with Investor X → talking points prepared
• GitHub: 2 new issues, 1 PR needs review
• Calendar conflict detected: moved standup to 10:30

Your top 3 priorities today:
1. Respond to investor follow-up (draft attached)
2. Review PR #47 (found a potential bug on line 203)
3. Prepare demo for Friday (outline started)
```

### Context Resurrection
```
You opened project "landing-page" (untouched for 23 days)

OmniBrain remembers:
• Last working on: hero section animation (components/Hero.tsx)
• Blocked on: Framer Motion performance on mobile
• Related conversation: You discussed this with Marco on Feb 2
• Solution found since then: React Spring is 3x faster for this use case
```

### Knowledge Graph Query
```
You: "What did Marco say about the pricing model?"

OmniBrain: Based on 3 conversations (email Feb 2, Telegram Feb 7, meeting Feb 11):

1. Freemium won't work for B2B (Feb 2, email)
2. Suggested $19/mo as sweet spot (Feb 7)
3. Agreed to do user interviews for validation (Feb 11)

No follow-up since Feb 11. Draft a reminder?
```

### Pattern Detection
```
I've noticed:
• Every Monday at 9am you search for flight prices to Milano
• You've done this 6 times in the past 2 months

Proposed automation:
"Every Sunday night, search flights and send top 3 options by Monday 8am"

[Enable] [Customize] [Not interested]
```

---

## Architecture at a Glance

```
┌──────────────────────────────────────────────────────────────┐
│                    OMNIBRAIN DAEMON (Python)                 │
│                    Always running via systemd                │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐    │
│  │  COLLECTOR   │  │  OMNIGENT    │  │  PROACTIVE       │    │
│  │  SERVICE     │  │  BRAIN       │  │  ENGINE          │    │
│  │              │  │              │  │                  │    │
│  │ Gmail API    │  │ Agent Loop   │  │ Pattern Detector │    │
│  │ Calendar API │  │ Reasoning    │  │ Priority Scorer  │    │
│  │ GitHub API   │  │ Graph        │  │ Action Proposer  │    │
│  │ File Watcher │  │ Planner      │  │ Scheduler        │    │
│  └──────┬───────┘  └──────┬───────┘  └────────┬─────────┘    │
│         │                 │                   │              │
│         ▼                 ▼                   ▼              │
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

Full technical deep-dive in [ARCHITECTURE.md](ARCHITECTURE.md).

---

## Current Status

**OmniBrain is at Day 0.** The codebase currently contains [Omnigent](https://github.com/FrancescoStabile/omnigent) — the agent framework that powers OmniBrain's reasoning, planning, and tool execution. All of OmniBrain's domain-specific intelligence will be built on top of this foundation.

See the [Roadmap](docs/ROADMAP.md) for what's coming and when.

### What's here now (Omnigent core):
- ReAct agent loop with circuit breaker, loop detection, rate limiting
- Multi-provider LLM routing (DeepSeek, Claude, OpenAI, Ollama)
- Reasoning Graph for multi-step chain reasoning
- Hierarchical task planner with phase-based execution
- Smart context management with semantic compression
- Domain Profile (structured agent memory)
- Extractor, reflector, and error recovery pipelines
- Plugin system with checksum verification
- Session persistence with checkpoint/replay
- Cost tracking per provider and task type
- 325+ passing tests

### What we're building:
- [ ] OmniBrain daemon (systemd service)
- [ ] Gmail + Google Calendar integration
- [ ] Morning briefing engine
- [ ] Telegram bot interface
- [ ] Proactive engine (pattern detection, action proposals)
- [ ] Semantic memory (ChromaDB)
- [ ] CLI + REST API
- [ ] Email drafting with approval flow
- [ ] Pattern detection + automation proposals
- [ ] Desktop app (Tauri)

---

## Why Local-First?

In 2026, "your data never leaves your computer" is not a feature — it's a requirement.

- **Your data stays on your machine.** Period.
- **No cloud.** No subscription to access your own memories.
- **No telemetry.** Zero data collection, zero phone-home, zero analytics.
- **You own everything.** Export, delete, migrate at any time.
- **Open source.** Verify every line. Fork it. Extend it.

OmniBrain uses cloud LLM APIs for reasoning, but you can switch entirely to local models (Ollama) for zero-cloud operation. Estimated cost with cloud APIs: **$0.50-$3/month**.

---

## Quick Start

OmniBrain is in early development. To follow along and contribute:

```bash
git clone https://github.com/FrancescoStabile/omnibrain.git
cd omnibrain
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

Follow [@Francesco_Sta](https://x.com/Francesco_Sta) on X for daily build updates.

---

## Project Structure

```
omnibrain/
├── src/omnigent/           # Omnigent core (the brain)
│   ├── agent.py            # ReAct loop, circuit breaker, loop detection
│   ├── router.py           # Multi-provider LLM routing
│   ├── reasoning_graph.py  # Directed graph for chain reasoning
│   ├── planner.py          # Hierarchical task planning
│   ├── context.py          # Smart context management
│   ├── domain_profile.py   # Structured agent memory
│   ├── state.py            # Agent state + Pydantic findings
│   ├── registry.py         # DomainRegistry dataclass
│   ├── extractors.py       # Tool result parsing pipeline
│   ├── reflection.py       # Post-tool strategic analysis
│   ├── error_recovery.py   # Pattern-matched recovery
│   ├── chains.py           # Escalation chain registry
│   ├── plugins.py          # Plugin system + checksums
│   ├── session.py          # Session persistence + checkpoints
│   ├── cost_tracker.py     # Cost tracking
│   └── tools/              # Tool registry
├── tests/                  # 325+ tests
├── docs/                   # Documentation & roadmap
├── manifesto.md            # The definitive vision document
├── ARCHITECTURE.md         # Technical architecture
├── CONTRIBUTING.md         # How to contribute
└── CHANGELOG.md            # Version history
```

---

## Contributing

OmniBrain is MIT-licensed. We welcome contributions of all kinds. See [CONTRIBUTING.md](CONTRIBUTING.md).

---

## Links

- **[Manifesto](manifesto.md)** — The complete vision, every schema, every decision
- **[Architecture](ARCHITECTURE.md)** — Technical deep-dive into OmniBrain + Omnigent
- **[Roadmap](docs/ROADMAP.md)** — Day-by-day build plan
- **[Omnigent](https://github.com/FrancescoStabile/omnigent)** — The agent framework powering OmniBrain
- **[X/Twitter](https://x.com/Francesco_Sta)** — Daily build-in-public updates

---

<div align="center">

**OmniBrain: The AI that never sleeps.**

Built by [Francesco Stabile](https://x.com/Francesco_Sta)

</div>
