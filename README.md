# rrm-ai

Small natural-language CLI for keeping a YAML status file up to date.

It is built for a personal RRM workflow: track active situations, waiting items,
follow-up dates, recurring duties, and today's focus. It is intentionally simple.
The YAML file is the source of truth, and the LLM is only used to interpret plain
English into validated patch operations.

```text
user text -> LLM patch proposal -> Python validation -> YAML update
```

The LLM never edits the YAML directly.

## Setup

Requirements:

- Python 3.11+
- `uv`
- an Anthropic API key for natural-language commands

Install for local development:

```bash
uv sync
cp .env.example .env
```

Edit `.env`:

```bash
RRM_AI_API_KEY=sk-...
RRM_AI_YAML=/absolute/path/to/rrm-status.yaml
RRM_AI_PROVIDER=anthropic
RRM_AI_MODEL=claude-sonnet-4-5-20250929
```

Keep `rrm-status.yaml` outside this repository. The repo is code; the YAML file
is your personal operational state.

Install the CLI from this checkout:

```bash
uv tool install --reinstall --editable .
```

## Usage

Show current state without calling the LLM:

```bash
rrm-ai --status
```

Ask questions:

```bash
rrm-ai "what is in focus today?"
rrm-ai "what am I waiting for?"
rrm-ai "summarize the current situation"
```

Request changes:

```bash
rrm-ai "put Project Atlas in waiting, I am waiting for Alex"
rrm-ai "mark Annual Report finished"
rrm-ai "add activation DEMO042 Northland, in progress"
rrm-ai "set the follow-up date for Project Atlas to 2026-03-15"
```

By default, changes show a diff and ask before writing:

```text
Proposed changes:
  * demo041  status: in_progress -> waiting
  * demo041  next_action: Prepare update when Alex replies.

Apply? [Y/n]
```

Useful flags:

```bash
rrm-ai "mark Annual Report finished" --dry-run
rrm-ai "mark Annual Report finished" --yes
rrm-ai --archive
```

`--archive` moves finished items to `rrm-archive.yaml`. Local commands such as
`--status` and `--archive` only need `RRM_AI_YAML`; they do not need an API key.

## YAML Format

Minimal item:

```yaml
- id: annual_report
  item: "Document: Annual Report"
  status: in_progress
  next_action: "Complete section 3 and send for review."
```

Supported fields:

| Field | Required | Meaning |
| --- | --- | --- |
| `id` | yes | Stable lowercase identifier |
| `item` | yes | Human-readable title |
| `status` | yes | `in_progress`, `waiting`, or `finished` |
| `next_action` | yes | Concrete next step |
| `today` | no | Daily focus flag, maximum 3 |
| `due` | no | Follow-up trigger date, `YYYY-MM-DD` |
| `recurs` | no | `weekly_fri`, `monthly_1`, or `monthly_last` |

Rules enforced by Python:

- `finished` is permanent.
- Recurring items cannot be `finished`.
- At most 3 items can have `today: true`.
- Invalid dates are rejected.
- Unknown patch operations are rejected.
- Empty `next_action` values are rejected.

## Development

Run the tests:

```bash
uv run pytest
```

Run a quick local status smoke test:

```bash
rrm-ai --status
```

Project entry point:

```toml
[project.scripts]
rrm-ai = "rrm_ai:main"
```

When adding a new top-level module, add it to `pyproject.toml` under
`[tool.setuptools].py-modules`.
