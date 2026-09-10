# Interactive Session — Design

Date: 2026-09-10
Status: approved, not implemented

## Purpose

`rrm-ai` is a one-shot CLI: every invocation is a fresh process, a fresh
LLM call, and a fresh exit. Updating three items means typing `rrm-ai`
three times and re-stating context the tool already had.

This spec adds a persistent interactive session: launch it, hold a real
conversation about operational state, apply or decline changes, quit.
Expected use is three to five short sessions a day.

## Scope

This is the first of four independent subsystems discussed. The other
three are out of scope and get their own specs:

| # | Subsystem | Status |
| --- | --- | --- |
| 1 | Interactive session | this spec |
| 2 | Linux desktop presence (launcher, tray, notifications) | later |
| 3 | Weekday autostart (systemd user timer) | later |
| 4 | Folder analysis — work directory vs YAML drift | later |

The session is also the foundation for two later interface forms: an
always-on TUI dashboard, then a hotkey-summoned overlay. The design
must not block either, which is why session logic and rendering are
separate modules.

Done means: launch `rrm-ai`, converse, apply a change, decline a
change, quit.

## Decisions

| Question | Decision |
| --- | --- |
| Usage pattern | Open, work, close. Three to five times a day. |
| Turn independence | Real conversation — a growing message thread. |
| Thread lifetime | Fresh each launch. The YAML is the memory. |
| Launch display | Local `--status` list. No LLM call, no API key needed. |
| Command surface | `/` prefix. Anything else goes to the LLM. |
| Declined patches | Recorded in the thread as explicitly not applied. |
| Input handling | `prompt_toolkit`. |

## Architecture

Two new modules, plus one extraction.

### `session.py` — frontend-agnostic core

Owns `yaml_path`, the adapter, the current `items` list, and the
message thread. No rendering, no user I/O. Its entire surface:

- `Session.start()` — load items, run auto-today promotion, return items
- `Session.submit(text)` — return `TextReply(markdown)` or
  `PatchProposal(ops, diffs)`; runs the validate-and-retry loop internally.
  Both are frozen dataclasses defined in `session.py`. `PatchProposal`
  carries the validated `ops` and the rendered `diffs` so the frontend
  displays without recomputing.
- `Session.accept(proposal)` — back up, write YAML, refresh `items`,
  record the applied turn, append to `rrm-history.json`
- `Session.decline(proposal)` — record the rejection turn, discard the ops

A later TUI calls exactly these four methods.

### `repl.py` — terminal frontend

`prompt_toolkit` for input, `rich` for output, slash-command dispatch,
the `Apply? [Y/n]` prompt. Knows nothing about the Anthropic API or
patch validation.

### `render.py` — extracted display

`print_status` moves here from `rrm_ai.py` so the one-shot path and the
REPL share it. Behavior unchanged, including the existing sort order.

### Unchanged

`adapters.py`, `patch.py`, `yaml_utils.py`, `auto_today.py`,
`config.py`, `theme.py`, `memory.py`.

`prompts.py` changes in exactly one way, described below.

## The conversation thread

### State freshness

`build_user_message` embeds the full YAML in the user message. In a
thread, every earlier message would hold a stale snapshot — five turns
means five contradictory copies of the state, and a patch built on one
of them writes to state that no longer exists.

**Rule: exactly one YAML snapshot exists per request, always in the
newest user message.**

`Session` stores turns as plain text — the naked user input, no state
block. At submit time it builds the request as prior turns verbatim,
then the current input wrapped by `build_user_message` with fresh
`items`. The snapshot is constructed per request and never retained.
The thread carries the conversation; the state block is current by
construction.

`build_user_message` needs no new behavior. The session calls it with
`history=None` — the thread supersedes the flat five-entry history.
`rrm-history.json` keeps being written: the one-shot path still reads
it, and it survives across sessions where the thread does not.

### Turn recording

| Outcome | Recorded |
| --- | --- |
| Query | User turn, assistant text reply. |
| Applied patch | User turn, assistant turn, then a synthetic user turn: `Applied. Current state follows.` |
| Declined patch | User turn, assistant turn, then a synthetic user turn: `NOT applied — the user declined this patch. The state is unchanged.` |
| Validation retry | Internal to `submit()`. Only the final proposal enters the thread. |

The declined wording is deliberately explicit. The failure to avoid is
the model later treating a proposed-but-declined change as done.

### Trimming

A turn means one message in the thread, user or assistant. Cap at 20,
dropping the oldest user/assistant pair first so the thread never begins
with an orphaned assistant message. The thread is fresh each launch, so
this only guards a runaway afternoon session.

### Prompt change

`prompts.py` currently instructs the model to treat a short affirmation
as confirming a pending change. That was a workaround for having no
thread. In a session, `Apply? [Y/n]` is handled in Python and never
reaches the LLM. **The `Confirmation handling` block is deleted**, so a
bare "yes" is never silently reinterpreted as re-applying something.

## The REPL

### Launch

`rrm-ai` with no arguments. Read YAML, run auto-today promotion, print
the item list, drop to the prompt. No API call and no API key needed
until the first non-command input.

### Commands

`/` prefix, exact match. Anything not starting with `/` goes to the LLM.

| Command | Effect |
| --- | --- |
| `/status` | Reprint the list from memory |
| `/brief` | LLM daily brief (the current bare-`rrm-ai` behavior) |
| `/archive` | Move finished items to the archive, then reprint |
| `/help` | List commands |
| `/quit` | Exit (`Ctrl-D` too) |

Unknown `/foo` prints `unknown command`. A typo must not cost an API call.

`/brief` is the one command that calls the LLM. It is a one-shot request
built from `build_daily_brief_prompt()` and does **not** enter the
thread — it is a report, not part of the conversation. Every other
command is local.

### Turn flow

Input, then a spinner during the API call, then either rendered
markdown (existing `LLM_MARKDOWN_THEME`) or the proposed-changes diff
followed by `Apply? [Y/n]`.

- `y` — apply, print `Applied.` and the refreshed list, so the result is
  visible rather than assumed
- `n` — print `Declined.`, record the rejection in the thread

### Input handling

`prompt_toolkit` with in-memory history (arrow-up) and completion on
`/` commands plus current item ids. Ids come from `session.items`, so
completion refreshes when a patch adds one.

### Error handling

A one-shot process can crash and lose nothing. A session cannot.

- API errors, network failures, and validation failures print a message
  and return to the prompt with the thread intact
- A failed turn is rolled back out of the thread rather than left
  half-written
- `Ctrl-C` at the prompt clears the current line
- `Ctrl-C` mid-request cancels that turn and returns to the prompt
- Only `/quit` and `Ctrl-D` exit

### Deliberately excluded

Live file-watching, background refresh, and configuration for any of
the above. These belong to the TUI phase if they earn their place.

## Migration

Bare `rrm-ai` stops printing a daily brief and launches the session.
A `--brief` flag preserves the old one-shot behavior; subsystem #3
(autostart) will need it.

Unchanged: `rrm-ai "text"`, `--status`, `--archive`, `--dry-run`,
`--yes`.

Checked on 2026-09-10: no shell alias, cron entry, or systemd unit
invokes bare `rrm-ai`. The only exposure is muscle memory.

## Dependencies

Adds `prompt_toolkit` to `pyproject.toml`.

Adds `session`, `repl`, and `render` to `[tool.setuptools].py-modules`.

## Testing

`session.py` is the target. A fake adapter returning canned results
makes every case deterministic and API-free:

- The thread carries prior turns; only the newest message holds a YAML snapshot
- Applying refreshes `items` and appends the `Applied.` turn
- Declining appends the `NOT applied` turn and leaves the YAML byte-identical
- A failed API call leaves the thread exactly as it was
- Trimming at 20 turns drops oldest first
- Validation retry stays internal; a corrected proposal enters the thread once

`repl.py` gets thin coverage: `/status` routes locally, non-slash text
routes to the session, unknown `/foo` never reaches the LLM. The
`prompt_toolkit` loop itself is verified manually.

Per the project guardrail, tests are added only where behavior is new.
Nothing in `patch.py`, `yaml_utils.py`, or `auto_today.py` changes, so
the existing 147 tests stay as they are. Two tests in `test_rrm_ai.py`
cover bare-invocation behavior and `print_status`'s location; both are
updated, not deleted.
