# {{SKILL_NAME}}

A Skill for [OmniBrain](https://github.com/FrancescoStabile/omnibrain).

## What it does

{{SKILL_DESCRIPTION}}

## Handlers

| File | Trigger | Purpose |
|------|---------|---------|
| `handlers/poll.py` | `schedule` | Periodic background task |
| `handlers/ask.py` | `on_ask` | Respond to user questions |
| `handlers/event.py` | `on_event` | React to system events |

## Permissions

This skill requires:
- `read_memory` — Read from OmniBrain's memory
- `notify` — Send notifications to the user
- `llm_access` — Use the configured LLM

## Development

```bash
# Scaffold from template
omnibrain-skill init my-skill

# Run tests
cd my-skill
omnibrain-skill test

# Install locally
cp -r my-skill ~/.omnibrain/skills/
```

## License

MIT
