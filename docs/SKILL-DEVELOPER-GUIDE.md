# Build Your First OmniBrain Skill in 30 Minutes

OmniBrain Skills are self-contained plugins that teach your AI new abilities — from
controlling smart-home devices to querying internal databases. This guide walks you
through creating, testing, and publishing a Skill from scratch.

---

## Table of Contents

1. [How Skills Work](#how-skills-work)
2. [Project Structure](#project-structure)
3. [Step 1: Scaffold](#step-1-scaffold)
4. [Step 2: Define Metadata](#step-2-define-metadata)
5. [Step 3: Implement a Tool](#step-3-implement-a-tool)
6. [Step 4: Add a Schema](#step-4-add-a-schema)
7. [Step 5: (Optional) Custom Extractor](#step-5-optional-custom-extractor)
8. [Step 6: (Optional) Knowledge Files](#step-6-optional-knowledge-files)
9. [Step 7: Test Locally](#step-7-test-locally)
10. [Step 8: Checksums & Security](#step-8-checksums--security)
11. [Publishing](#publishing)
12. [API Reference](#api-reference)

---

## How Skills Work

```
~/.omnigent/plugins/
  my-skill/
    __init__.py        # PLUGIN_META dict (required)
    plugin.json        # manifest (recommended)
    tool.py            # tool functions
    extractor.py       # custom extractors (optional)
    knowledge/         # markdown/txt context files (optional)
    checksums.json     # SHA-256 hashes for integrity (optional)
```

On startup, the **PluginManager** scans `~/.omnigent/plugins/`, reads metadata,
verifies optional checksums, and dynamically loads tools, extractors, and knowledge
into the running agent.

### Plugin types

| Type        | What it adds                              |
|-------------|-------------------------------------------|
| `tool`      | Callable functions the LLM can invoke     |
| `extractor` | Custom data-extraction pipeline stages    |
| `knowledge` | Markdown/text files injected into context |
| `all`       | All of the above                          |

---

## Project Structure

```
my-weather-skill/
├── __init__.py          # PLUGIN_META + optional inline registrations
├── plugin.json          # Structured metadata (overrides __init__.py)
├── tool.py              # Tool implementations (TOOLS dict)
├── extractor.py         # Optional: EXTRACTORS dict
├── knowledge/
│   └── weather-api.md   # Optional: reference docs for the LLM
└── checksums.json       # Optional: SHA-256 integrity check
```

---

## Step 1: Scaffold

```bash
mkdir -p ~/.omnigent/plugins/my-weather-skill/knowledge
cd ~/.omnigent/plugins/my-weather-skill
touch __init__.py tool.py plugin.json
```

---

## Step 2: Define Metadata

### Option A — `plugin.json` (recommended)

```json
{
  "name": "my-weather-skill",
  "version": "1.0.0",
  "type": "tool",
  "description": "Fetch current weather for any city",
  "author": "your-name",
  "enabled": true
}
```

Required fields: `name`, `version`, `type`.

### Option B — `PLUGIN_META` in `__init__.py`

```python
PLUGIN_META = {
    "name": "my-weather-skill",
    "version": "1.0.0",
    "type": "tool",
    "description": "Fetch current weather for any city",
    "author": "your-name",
}
```

If both exist, `plugin.json` takes precedence.

---

## Step 3: Implement a Tool

Create **`tool.py`** — export a `TOOLS` dict mapping function names to callables,
and a `TOOL_SCHEMAS` dict mapping names to JSON-Schema-style parameter descriptions:

```python
"""my-weather-skill — tool implementation."""

import urllib.request
import json


def get_weather(city: str) -> dict:
    """Return current weather for a city using wttr.in."""
    url = f"https://wttr.in/{city}?format=j1"
    with urllib.request.urlopen(url, timeout=10) as resp:
        data = json.loads(resp.read())
    current = data["current_condition"][0]
    return {
        "city": city,
        "temp_c": current["temp_C"],
        "temp_f": current["temp_F"],
        "condition": current["weatherDesc"][0]["value"],
        "humidity": current["humidity"],
        "wind_kmph": current["windspeedKmph"],
    }


# ── Exports ──────────────────────────────────────────────────────────────

TOOLS = {
    "get_weather": get_weather,
}

TOOL_SCHEMAS = {
    "get_weather": {
        "description": "Get current weather for a city",
        "parameters": {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "City name (e.g. 'Rome', 'New York')",
                },
            },
            "required": ["city"],
        },
    },
}
```

**Key rules:**
- Tool functions must be **synchronous** or **async** — both are supported.
- Return a `dict`, `str`, or any JSON-serializable value.
- Raise exceptions for errors — the agent will surface them gracefully.
- Keep dependencies minimal. stdlib is always available; for third-party libs,
  document requirements clearly.

---

## Step 4: Add a Schema

The schema in `TOOL_SCHEMAS` follows JSON Schema format. This tells the LLM what
parameters your tool accepts:

```python
TOOL_SCHEMAS = {
    "my_tool": {
        "description": "One-line description for the LLM",
        "parameters": {
            "type": "object",
            "properties": {
                "param1": {"type": "string", "description": "What it does"},
                "param2": {"type": "integer", "description": "Optional number", "default": 10},
            },
            "required": ["param1"],
        },
    },
}
```

Use clear descriptions — the LLM reads them to decide when and how to call your tool.

---

## Step 5: (Optional) Custom Extractor

If your Skill needs to extract structured data from raw inputs, create **`extractor.py`**:

```python
"""Custom extractor for flight data."""

import re

def extract_flight_info(text: str) -> dict | None:
    """Extract flight numbers from text."""
    match = re.search(r'\b([A-Z]{2}\d{3,4})\b', text)
    if match:
        return {"flight_number": match.group(1)}
    return None


EXTRACTORS = {
    "flight_info": extract_flight_info,
}
```

Extractors are called during the extraction pipeline and their output is merged
into the agent's working context.

---

## Step 6: (Optional) Knowledge Files

Place `.md` or `.txt` files in a `knowledge/` subdirectory. These are loaded into
the agent's context for RAG-style retrieval:

```markdown
<!-- knowledge/weather-api.md -->
# Weather API Notes

- wttr.in supports city names, airport codes, and coordinates
- Rate limit: ~100 requests/hour per IP
- Append `?format=j1` for JSON output
```

Knowledge files are indexed with SQLite FTS5 and retrieved when the user's query
matches relevant terms.

---

## Step 7: Test Locally

### Quick smoke test

```bash
# Start OmniBrain
cd /path/to/omnibrain
python -m omnigent

# In another terminal, test the tool directly
curl -X POST http://127.0.0.1:7432/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What is the weather in Rome?"}'
```

### Verify plugin loaded

Check the server logs for:

```
INFO  omnigent.plugins: Discovered plugin: my-weather-skill v1.0.0 (tool)
INFO  omnigent.plugins: Loaded plugin: my-weather-skill (tools: 1, extractors: 0, knowledge: 0)
```

### Unit test your tool

```python
# test_my_weather_skill.py
from pathlib import Path
import sys

# Add your plugin to the path
sys.path.insert(0, str(Path.home() / ".omnigent/plugins/my-weather-skill"))

from tool import get_weather

def test_get_weather():
    result = get_weather("London")
    assert "city" in result
    assert "temp_c" in result
    assert result["city"] == "London"
```

---

## Step 8: Checksums & Security

For distribution, generate a `checksums.json` so OmniBrain can verify file integrity:

```bash
cd ~/.omnigent/plugins/my-weather-skill

python3 -c "
import hashlib, json, pathlib

files = ['__init__.py', 'tool.py', 'plugin.json']
checksums = {}
for f in files:
    p = pathlib.Path(f)
    if p.exists():
        checksums[f] = hashlib.sha256(p.read_bytes()).hexdigest()

pathlib.Path('checksums.json').write_text(json.dumps(checksums, indent=2))
print('Generated checksums.json')
"
```

When `checksums.json` is present, OmniBrain verifies SHA-256 hashes before loading
any plugin code. In **strict mode** (`strict_checksums=True`), plugins *without*
checksums are rejected entirely.

---

## Publishing

1. Package your Skill directory as a `.tar.gz` or zip:
   ```bash
   tar czf my-weather-skill-1.0.0.tar.gz my-weather-skill/
   ```

2. Users install by extracting into `~/.omnigent/plugins/`:
   ```bash
   tar xzf my-weather-skill-1.0.0.tar.gz -C ~/.omnigent/plugins/
   ```

3. Restart OmniBrain — the Skill appears in the Skill Store automatically.

The Skill Store UI reads plugin metadata and shows install/enable/disable controls.
No additional registration is needed.

---

## API Reference

### PluginMeta fields

| Field         | Type   | Default   | Description                      |
|---------------|--------|-----------|----------------------------------|
| `name`        | str    | required  | Unique skill identifier          |
| `version`     | str    | `"0.1.0"` | SemVer version string            |
| `description` | str    | `""`      | Short description for the Store  |
| `author`      | str    | `""`      | Author name or handle            |
| `type`        | str    | `"tool"`  | `tool` / `extractor` / `knowledge` / `all` |
| `enabled`     | bool   | `true`    | Whether to load on startup       |

### TOOLS dict

```python
TOOLS: dict[str, Callable] = {
    "function_name": function_reference,
}
```

### TOOL_SCHEMAS dict

```python
TOOL_SCHEMAS: dict[str, dict] = {
    "function_name": {
        "description": "What the tool does (LLM reads this)",
        "parameters": {  # JSON Schema
            "type": "object",
            "properties": { ... },
            "required": [ ... ],
        },
    },
}
```

### EXTRACTORS dict

```python
EXTRACTORS: dict[str, Callable[[str], dict | None]] = {
    "extractor_name": extractor_function,
}
```

### Knowledge files

Any `.md` or `.txt` file in `knowledge/` is auto-indexed. No code needed.

---

## Tips

- **Keep tools focused** — one tool per action. The LLM decides which to call.
- **Return structured data** — dicts are easier for the LLM to reason about.
- **Use clear schema descriptions** — they're the LLM's only documentation.
- **Handle errors gracefully** — raise with a descriptive message.
- **Minimize dependencies** — stdlib-only Skills are the most portable.
- **Version your Skills** — bump `version` on every change for clean upgrades.

---

*Happy building!* 🧠
