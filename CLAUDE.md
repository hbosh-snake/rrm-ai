# CLAUDE.md — Project Guide

## What this is

`rrm-ai` is a natural language CLI for managing operational RRM situations. An LLM interprets user input into structured patch operations; Python validates and applies them to a YAML file.

Keep it lightweight and explicit. No new architecture without a clear need.

---

## Current state

All optional fields (`today`, `due`, `recurs`) are fully implemented and stable:

- `patch.py`: validation, apply logic, cross-field invariants
- `adapters.py`: tool schema and parser support all six ops (`set_status`, `set_today`, `set_next_action`, `set_due`, `set_recurs`, `add_item`)
- `yaml_utils.py`: read/write/diff handle optional fields
- `auto_today.py`: promotes `due` and `recurs` items to `today` automatically
- Test suite: 147 tests, all green

---

## Display order (`--status`)

Items are sorted: `today: true` first, then by status (`in_progress` → `waiting`), then the rest.

---

## Guardrails

- No behavior expansion without a clear user need.
- No unnecessary abstractions.
- Keep data model flat and explicit.
- Prefer deleting tests over adding new ones when behavior is duplicated.
- Every kept test must justify its maintenance cost.

---

## Development

```bash
uv run pytest          # run all tests
uv run pytest -v       # verbose

uv tool install --reinstall --editable .   # reinstall CLI after changes
```

Every new module must be added to `py-modules` in `pyproject.toml` before reinstalling.
