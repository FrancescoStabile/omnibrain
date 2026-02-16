# Built-in Skills

These are the 5 Skills that ship with OmniBrain on Day 1.

Each Skill follows the [Skill Protocol](../docs/SKILL-PROTOCOL.md) and can be used
as a reference implementation for building custom Skills.

| Skill | Description | Source |
|-------|-------------|--------|
| `email-manager` | Gmail triage, drafts, smart replies | Extracted from `integrations/gmail.py` |
| `calendar-assistant` | Events, meeting briefs, conflicts | Extracted from `integrations/calendar.py` |
| `morning-briefing` | Daily summary with priorities | Extracted from `briefing.py` |
| `memory-search` | "What did [person] say?" queries | Extracted from `memory.py` + `knowledge_graph.py` |
| `pattern-detector` | Behavioral patterns + automation | Extracted from `proactive/patterns.py` |

## Building a Skill

See [docs/SKILL-PROTOCOL.md](../docs/SKILL-PROTOCOL.md) for the complete specification.

Quick start:
```bash
omnibrain-skill init my-skill
cd my-skill
# Edit skill.yaml and handlers/
omnibrain-skill test
omnibrain-skill publish
```
