<div align="center">

# OmniBrain

**Your AI must be yours.**

An open-source AI platform that knows who you are, remembers everything, works 24/7, and grows smarter through community-built Skills.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-1650%2B%20passing-brightgreen.svg)]()
[![Build in Public](https://img.shields.io/badge/build%20in%20public-daily%20on%20X-black.svg)](https://x.com/Francesco_Sta)

[Manifesto](manifesto.md) · [Docs](docs/INDEX.md) · [Skill Protocol](docs/SKILL-PROTOCOL.md) · [Contributing](CONTRIBUTING.md)

</div>

---

## Install in 2 Minutes

```bash
git clone https://github.com/FrancescoStabile/omnibrain
cd omnibrain
cp .env.example .env   # add your API key
docker compose up
# Open http://localhost:3000
```

That's it. Your data stays on your machine. Always.

---

## The Problem

8 billion people talk to AI every day. None of these AIs know who they are.

Every conversation starts from zero. Your digital life is chaos — emails, meetings, subscriptions, promises you made 3 months ago, information scattered across 15 apps. Current AI is reactive: you open the app, you formulate the question, you provide context, and it forgets everything when you close the tab.

## The Solution

OmniBrain is a **personal AI platform** that:

- **Knows you** — Connects to your email, calendar, and more. Builds a personal knowledge graph.
- **Remembers everything** — Full-text search + semantic memory. "What did Marco say about pricing?" → instant answer with sources.
- **Works while you sleep** — Proactive engine detects patterns, proposes actions, prepares morning briefings.
- **Grows through Skills** — Open Skill Protocol lets anyone teach it new abilities. Like extensions for VS Code.
- **Stays private** — Local-first. Your data never leaves your machine. Open source. MIT license.

```
While you slept (23:47 → 06:30):

✓ Triaged 12 emails (3 urgent, 4 FYI, 5 archived)
✓ Found unanswered email from Marco (3 days ago) → draft ready
✓ Detected unused subscription: €14.99/mo → cancellation link ready
✓ Prepared morning briefing with today's meetings + talking points

All actions are PROPOSALS. Nothing sent without your approval.
```

---

## Why Platform, Not Product

Every other personal AI is a monolith. One team building one product. That doesn't scale.

We build the **brain** — memory, reasoning, proactivity. Then we open a **Skill Protocol** so anyone can teach it new abilities.

| Platform | Core | Extensions | Result |
|----------|------|------------|--------|
| VS Code | Editor | 50,000+ extensions | Killed every rival |
| Obsidian | Markdown editor | 1,800+ plugins | Cult following |
| **OmniBrain** | **AI Brain** | **Community Skills** | **The AI that becomes you** |

### Built-in Skills

| Skill | What It Does |
|-------|-------------|
| 📧 Email Manager | Gmail triage, drafts, smart replies |
| 📅 Calendar Assistant | Events, meeting briefs, conflict detection |
| 🌅 Morning Briefing | Daily summary with priorities |
| 🧠 Memory Search | "What did [person] say about [topic]?" |
| 🔍 Pattern Detector | Behavioral patterns + automation proposals |

### Build Your Own Skill

```yaml
# skill.yaml
name: spotify-tracker
version: 1.0.0
description: "Track your listening patterns"
triggers:
  - schedule: "every 1h"
  - on_ask: "music|spotify|listening"
permissions:
  - read_memory
  - write_memory
  - notify
```

### Create Your Own Skill

```bash
# Scaffold a new skill in 10 seconds
omnibrain-skill init my-awesome-skill --category productivity

# Generated structure:
# my-awesome-skill/
# ├── skill.yaml        ← manifest (triggers, permissions)
# ├── handlers/
# │   ├── poll.py       ← periodic background task
# │   ├── ask.py        ← user question handler
# │   └── event.py      ← system event handler
# ├── tests/
# │   └── test_handlers.py
# └── README.md

# Run tests
omnibrain-skill test

# Install locally
cp -r my-awesome-skill ~/.omnibrain/skills/
```

Full spec: [docs/SKILL-PROTOCOL.md](docs/SKILL-PROTOCOL.md) · Developer guide: [docs/SKILL-DEVELOPER-GUIDE.md](docs/SKILL-DEVELOPER-GUIDE.md)

---

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                    WEB UI (Next.js)                       │
│    Chat  │  Proactive Feed  │  Skill Store  │  Settings  │
└────────────────────────┬─────────────────────────────────┘
                         │  REST + WebSocket
┌────────────────────────┴─────────────────────────────────┐
│                   API LAYER (FastAPI)                      │
└────────────────────────┬─────────────────────────────────┘
┌────────────────────────┴─────────────────────────────────┐
│                     THE BRAIN (Python)                     │
│                                                           │
│  Agent Engine  │  Memory Layer  │  Proactive Engine       │
│  (ReAct loop,  │  (SQLite FTS5, │  (Patterns, Scorer,    │
│   Reasoning    │   Knowledge    │   Proposer, Briefings) │
│   Graph)       │   Graph)       │                        │
│                                                           │
│  ┌─────────────────────────────────────────────────────┐ │
│  │              SKILL RUNTIME                           │ │
│  │  Loads Skills → Sandboxes → Routes triggers          │ │
│  └─────────────────────────────────────────────────────┘ │
│  ┌─────────────────────────────────────────────────────┐ │
│  │              LLM ROUTER                              │ │
│  │  DeepSeek ($0.14/M) │ Claude │ OpenAI │ Ollama      │ │
│  └─────────────────────────────────────────────────────┘ │
│  ┌─────────────────────────────────────────────────────┐ │
│  │              APPROVAL GATE                           │ │
│  │  Nothing sends without your OK. Ever.                │ │
│  └─────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

Deep dive: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

---

## Quick Start

### Docker (recommended)

```bash
git clone https://github.com/FrancescoStabile/omnibrain.git
cd omnibrain
cp .env.example .env
# Edit .env — add at least one LLM API key
docker compose up -d
# Open http://localhost:3000
```

### From source

```bash
git clone https://github.com/FrancescoStabile/omnibrain.git
cd omnibrain
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -x -q            # 1608+ tests should pass
cp .env.example .env    # add your API keys
omnibrain start          # Backend on :7432
cd web && npm install && npm run dev  # Frontend on :3000
```

### Configuration

```bash
# LLM Provider (at least one required)
DEEPSEEK_API_KEY=sk-...          # Cheap ($0.50/mo average)
ANTHROPIC_API_KEY=sk-ant-...     # Smart (for complex reasoning)
OPENAI_API_KEY=sk-...            # Alternative

# Google APIs (for Email + Calendar Skills)
GOOGLE_CREDENTIALS_PATH=~/.omnibrain/credentials.json
```

---

## Project Structure

```
omnibrain/
├── manifesto.md                 # The Bible — single source of truth
├── docs/                        # Full documentation (14 docs)
│
├── src/omnigent/                # Agent framework (the brain's brain)
│   ├── agent.py                 # ReAct loop (1025 lines)
│   ├── router.py                # Multi-provider LLM router
│   ├── reasoning_graph.py       # Directed reasoning graph
│   ├── planner.py               # Hierarchical planner
│   ├── plugins.py               # Plugin system → base for Skill Protocol
│   └── ...                      # Context, session, cost tracking, etc.
│
├── src/omnibrain/               # Platform application
│   ├── daemon.py                # Main process orchestrator
│   ├── memory.py                # SQLite FTS5 + ChromaDB memory
│   ├── knowledge_graph.py       # Entity-relationship queries
│   ├── briefing.py              # Morning/evening/weekly briefings
│   ├── approval.py              # 3-level approval gate
│   ├── prompt_injection.py      # 16+ pattern injection defense
│   ├── proactive/               # Engine, patterns, scorer
│   ├── integrations/            # Gmail, Calendar → become Skills
│   ├── interfaces/              # API server, Telegram bot
│   └── tools/                   # Email, calendar, memory tools
│
├── skills/                      # Built-in Skills (Skill Protocol)
├── marketplace/                 # Community skill registry
├── web/                         # Web UI (Next.js + shadcn/ui)
├── scripts/                     # Install, systemd, Google setup
└── tests/                       # 1650+ passing tests
```

---

## Status

**1650+ tests passing.** Core engine, memory, knowledge graph, proactive engine, briefings, approval, Gmail, Calendar, Web UI, Skill Runtime, sandbox isolation, preference learning, transparency logging, GDPR data export/wipe — all built and tested.

Building in public: [@Francesco_Sta on X](https://x.com/Francesco_Sta)

---

## Contributing

We welcome contributions of all kinds — especially **Skills**. See [CONTRIBUTING.md](CONTRIBUTING.md).

**Ways to contribute:**
- 🔧 Build a Skill (the highest-impact contribution)
- 🐛 Report bugs / fix issues
- 🎨 Improve the Web UI
- 📝 Write documentation
- 🧪 Add tests

---

## Documentation

| Document | Description |
|----------|-------------|
| [Manifesto](manifesto.md) | The single source of truth |
| [Vision](docs/VISION.md) | Why this exists, who it's for |
| [Architecture](docs/ARCHITECTURE.md) | System design, tech decisions |
| [Skill Protocol](docs/SKILL-PROTOCOL.md) | Build a Skill in 30 minutes |
| [API Spec](docs/API-SPEC.md) | Every endpoint |
| [UX Bible](docs/UX-BIBLE.md) | Design system |
| [All docs →](docs/INDEX.md) | Full documentation index |

---

## License

MIT — free for everyone, forever. See [LICENSE](LICENSE).

---

<div align="center">

**OmniBrain: The AI that becomes you.**

Built by [Francesco Stabile](https://x.com/Francesco_Sta) + [Claude Opus 4.6](https://anthropic.com)

</div>
