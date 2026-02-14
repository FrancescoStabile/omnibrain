# Contributing to OmniBrain

OmniBrain is built in public by [Francesco Stabile](https://x.com/Francesco_Sta) and Claude Opus 4.6. We welcome contributions from anyone who shares the vision of a local-first, proactive, open-source personal AI.

## Ways to Contribute

- **Bug reports** — Open an issue with a minimal reproduction
- **Feature requests** — Describe the use case, not just the solution
- **Code** — Fix bugs, improve performance, add tests, implement features from the [Roadmap](docs/ROADMAP.md)
- **Documentation** — Fix typos, clarify concepts, add examples
- **Integrations** — Build new data source connectors or interface channels
- **Testing** — Use OmniBrain daily and report your real experience

## Development Setup

```bash
# Clone the repo
git clone https://github.com/FrancescoStabile/omnibrain.git
cd omnibrain

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install in development mode with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run linter
ruff check src/
```

## Code Style

- **Python 3.11+** with type hints everywhere
- **Ruff** for linting (config in pyproject.toml)
- Docstrings on all public classes and functions
- Tests for all new functionality

## Architecture Guidelines

Before contributing, read [ARCHITECTURE.md](ARCHITECTURE.md) and the [Manifesto](manifesto.md).

**Key principles:**

1. **Omnigent core stays domain-agnostic.** No OmniBrain-specific logic in `src/omnigent/`. All personal AI behavior goes through registries, subclass hooks, or dedicated `src/omnibrain/` modules.

2. **Local-first always.** Every feature must work without cloud services. Cloud LLMs are optional — Ollama must always be an alternative.

3. **Never act without approval.** Any feature that sends data externally (email, message, API call) MUST go through the approval gate. No exceptions.

4. **Never crash.** All extension points (extractors, reflectors, integrations) must catch exceptions. A Gmail API error must never stop the daemon.

5. **Privacy by default.** No telemetry, no analytics, no data collection. User data never leaves the machine unless the user explicitly approves an action.

## Pull Request Process

1. Fork the repo and create a feature branch from `main`
2. Write tests for your changes
3. Ensure all tests pass: `pytest`
4. Ensure linting passes: `ruff check src/`
5. Update documentation if needed
6. Submit a PR with a clear description of **what** and **why**

## What to Work On

Check the [Roadmap](docs/ROADMAP.md) for current priorities. Issues labeled `good first issue` are a great starting point.

**High-impact areas:**
- Integration connectors (Gmail, Calendar, GitHub)
- Telegram bot features
- CLI commands
- Test coverage
- Documentation and examples

## Legal Notes

### EU AI Act Compliance
OmniBrain must comply with the EU AI Act. Key rules:
- AI-generated content must be clearly labeled
- OmniBrain must identify itself as AI in all communications
- No impersonation of the user
- No emotional manipulation claims

### Privacy
- All data stays local by default
- User can delete all data with one command
- User can export all data (JSON/CSV)

## Reporting Security Issues

If you find a security vulnerability, **do not** open a public issue. Email the maintainer directly.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
