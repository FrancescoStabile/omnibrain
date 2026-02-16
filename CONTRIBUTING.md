# Contributing to OmniBrain

OmniBrain is built in public by [Francesco Stabile](https://x.com/Francesco_Sta) and Claude Opus 4.6. We welcome contributions from anyone who shares the vision of an open-source personal AI platform.

## Ways to Contribute

| Impact | Contribution |
|--------|-------------|
| 🔧 **Highest** | Build a Skill — see [Skill Protocol](docs/SKILL-PROTOCOL.md) |
| 🎨 **High** | Improve the Web UI (`web/`) |
| 🐛 **High** | Fix bugs, improve stability |
| 🧪 **Medium** | Add tests (currently 983 passing) |
| 📝 **Medium** | Improve documentation |
| 💡 **Any** | Feature requests + bug reports |

## Development Setup

```bash
git clone https://github.com/FrancescoStabile/omnibrain.git
cd omnibrain

# Python backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest -x -q  # 983 tests should pass

# Web UI (requires Node.js 20+)
cd web
npm install
npm run dev
```

## Code Style

### Python
- **Python 3.11+** with type hints on all function signatures
- **Ruff** for linting (config in `pyproject.toml`)
- **Black** formatting (line length 88)
- Docstrings on all public classes and functions
- Async for all I/O-bound functions

### TypeScript (Web UI)
- ESLint + Prettier
- Strict TypeScript — no `any`
- Functional components with hooks
- Tailwind CSS utility classes

## Architecture Rules

1. **Omnigent stays domain-agnostic.** No OmniBrain-specific logic in `src/omnigent/`. Extend via registries and subclass hooks.
2. **Local-first always.** Every feature must work without cloud services. Ollama is always an alternative.
3. **Never act without approval.** Anything that sends data externally MUST go through the approval gate. No exceptions.
4. **Never crash.** All extension points wrap execution in try/except. A Gmail API error must never stop the daemon.
5. **No telemetry.** Zero data collection, zero phone-home.

## Building a Skill

The highest-impact contribution is a Skill. Start here:

1. Read [docs/SKILL-PROTOCOL.md](docs/SKILL-PROTOCOL.md)
2. Fork the [skill template](https://github.com/omnibrain/skill-template) (coming soon)
3. Build your Skill (30 minutes for a simple one)
4. Test with `omnibrain-skill test`
5. Submit to the Skill registry

## Pull Request Process

1. Fork and branch from `main`
2. Write tests for your changes
3. Ensure all tests pass: `pytest -x -q`
4. Ensure linting passes: `ruff check src/`
5. Submit PR with a clear description of **what** and **why**

## Commit Messages

```
feat: add Spotify Skill with listening patterns
fix: correct timezone handling in briefing scheduler
docs: update Skill Protocol examples
test: add calendar conflict detection tests
```

## Security

If you find a security vulnerability, **do not** open a public issue. Email the maintainer directly.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
