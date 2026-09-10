# Interactive Session Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn `rrm-ai` from a one-shot CLI into a persistent interactive session that holds a real conversation, proposes patches, and applies or declines them.

**Architecture:** A frontend-agnostic `Session` core owns the items, the adapter, and the message thread; a thin `repl.py` frontend owns `prompt_toolkit` input, `rich` output, and slash commands. Display code moves to `render.py` so the one-shot path and the REPL share it. Exactly one YAML snapshot exists per request, always in the newest user message.

**Tech Stack:** Python 3.11+, `anthropic`, `ruamel.yaml`, `rich`, `prompt_toolkit`, `pytest`, `uv`.

**Spec:** `docs/superpowers/specs/2026-09-10-interactive-session-design.md`

## Global Constraints

- Package manager is `uv`. Always `uv run pytest`, never `python3 -m pytest`. Always `uv add`, never `pip install`.
- Every new top-level module must be added to `[tool.setuptools].py-modules` in `pyproject.toml`.
- No emojis in code.
- The Anthropic Messages API requires strictly alternating user/assistant roles. The thread must always begin with a user message and never contain two consecutive messages of the same role.
- Exactly one YAML snapshot per request, in the newest user message. Thread entries store naked user text, never a state block.
- Thread cap is 20 messages, dropping the oldest user/assistant pair first.
- Do not modify `patch.py`, `yaml_utils.py`, `auto_today.py`, `config.py`, `theme.py`, or `adapters.py`.
- Existing tests must stay green except the two in `test_rrm_ai.py` that Task 1 and Task 8 explicitly update.

---

### Task 1: Extract display into `render.py`

Pure refactor. `print_status` moves out of `rrm_ai.py` so both frontends share it.

**Files:**
- Create: `render.py`
- Modify: `rrm_ai.py` (delete `print_status`, import from `render`)
- Modify: `pyproject.toml` (add `render` to `py-modules`)
- Test: `tests/test_render.py` (create), `tests/test_rrm_ai.py` (update import)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `render.print_status(items: list, console: Console | None = None) -> None`

- [ ] **Step 1: Write the failing test**

Create `tests/test_render.py`:

```python
from rich.console import Console

from render import print_status


def test_print_status_emits_ansi_codes(capsys):
    items = [{"id": "x", "item": "Some task", "status": "in_progress",
              "today": False, "next_action": "do it"}]
    print_status(items, console=Console(force_terminal=True))
    output = capsys.readouterr().out
    assert "\x1b[" in output


def test_print_status_today_marker_present(capsys):
    items = [{"id": "z", "item": "Focus task", "status": "in_progress",
              "today": True, "next_action": "focus"}]
    print_status(items, console=Console())
    output = capsys.readouterr().out
    assert "*" in output


def test_print_status_no_today_marker_when_false(capsys):
    items = [{"id": "z", "item": "Task", "status": "waiting",
              "today": False, "next_action": "wait"}]
    print_status(items, console=Console())
    output = capsys.readouterr().out
    assert "*" not in output


def test_today_items_sort_first(capsys):
    items = [
        {"id": "later", "item": "B", "status": "in_progress",
         "today": False, "next_action": "b"},
        {"id": "focus", "item": "A", "status": "waiting",
         "today": True, "next_action": "a"},
    ]
    print_status(items, console=Console())
    output = capsys.readouterr().out
    assert output.index("focus") < output.index("later")


def test_due_and_recurs_hints_rendered(capsys):
    items = [{"id": "r", "item": "Recurring", "status": "in_progress",
              "today": False, "next_action": "do",
              "due": "2026-09-30", "recurs": "weekly_fri"}]
    print_status(items, console=Console())
    output = capsys.readouterr().out
    assert "due: 2026-09-30" in output
    assert "recurs: weekly_fri" in output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_render.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'render'`

- [ ] **Step 3: Create `render.py`**

Move the function verbatim out of `rrm_ai.py`:

```python
from rich.console import Console
from rich.markup import escape

from theme import THEME, STATUS_STYLES

STATUS_ORDER = {"in_progress": 0, "waiting": 1}


def _sort_key(item):
    today_rank = 0 if item.get("today") else 1
    status_rank = STATUS_ORDER.get(item.get("status"), 2)
    return (today_rank, status_rank)


def print_status(items: list, console: Console | None = None) -> None:
    """Print items sorted today-first, then by status."""
    if console is None:
        console = Console()

    for item in sorted(items, key=_sort_key):
        status = item["status"]
        style = STATUS_STYLES.get(status, "")
        today_marker = f" [{THEME['today_marker']}]*[/]" if item.get("today") else ""
        id_part = f"[{THEME['item_id']}]{escape(item['id'])}[/]"
        status_tag = f"[{style}]{escape(f'[{status}]')}[/]"
        console.print(
            f"  {status_tag}{today_marker}  {id_part}  {escape(item['item'])}"
        )

        next_part = f"[{THEME['next_action']}]{escape(item['next_action'])}[/]"
        line2 = f"      next: {next_part}"

        hints = []
        if item.get("due"):
            hints.append(
                f"[{THEME['optional_field']}]due: {escape(str(item['due']))}[/]"
            )
        if item.get("recurs"):
            hints.append(
                f"[{THEME['optional_field']}]recurs: {escape(str(item['recurs']))}[/]"
            )
        if hints:
            line2 += "  " + "  ".join(hints)

        console.print(line2)
```

- [ ] **Step 4: Delete `print_status` from `rrm_ai.py` and import it**

In `rrm_ai.py`, delete the whole `print_status` function and the now-unused `escape` and `STATUS_STYLES` imports. Add to the import block:

```python
from render import print_status
```

Keep `from theme import THEME, LLM_MARKDOWN_THEME` — `THEME` is still used by `main()`.

- [ ] **Step 5: Update `tests/test_rrm_ai.py`**

Change the import line:

```python
from rrm_ai import main
from render import print_status
```

Then delete the three `print_status` tests from `TestColoredOutput` (`test_print_status_emits_ansi_codes`, `test_print_status_today_marker_present`, `test_print_status_no_today_marker_when_false`) — they now live in `tests/test_render.py`. Keep the other tests in that class.

- [ ] **Step 6: Add `render` to `pyproject.toml`**

```toml
py-modules = ["rrm_ai", "adapters", "config", "patch", "prompts", "yaml_utils", "memory", "theme", "daily_brief", "auto_today", "render"]
```

- [ ] **Step 7: Run the full suite**

Run: `uv run pytest`
Expected: PASS, all tests green.

- [ ] **Step 8: Commit**

```bash
git add render.py rrm_ai.py pyproject.toml tests/test_render.py tests/test_rrm_ai.py
git commit -m "refactor: extract print_status into render.py"
```

---

### Task 2: Fix `format_patch_result` for `set_due` and `set_recurs`

`format_patch_result` today silently drops both op types, producing an empty string for a due-date change. The session uses it for assistant turn text, so the gap would make applied changes invisible to the thread.

**Files:**
- Modify: `memory.py:38-51`
- Test: `tests/test_memory.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `memory.format_patch_result(ops: list[PatchOp]) -> str` now covers all six ops.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_memory.py`:

```python
def test_format_patch_result_covers_set_due():
    ops = [PatchOp(op="set_due", id="demo041", value="2026-10-01")]
    assert format_patch_result(ops) == "set_due(demo041, 2026-10-01)"


def test_format_patch_result_covers_set_recurs():
    ops = [PatchOp(op="set_recurs", id="demo041", value="weekly_fri")]
    assert format_patch_result(ops) == "set_recurs(demo041, weekly_fri)"


def test_format_patch_result_covers_clearing_due():
    ops = [PatchOp(op="set_due", id="demo041", value=None)]
    assert format_patch_result(ops) == "set_due(demo041, None)"
```

Make sure the file imports what it needs:

```python
from memory import format_patch_result
from patch import PatchOp
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_memory.py -v -k format_patch_result`
Expected: FAIL — `set_due` returns `""` rather than `"set_due(demo041, 2026-10-01)"`

- [ ] **Step 3: Add the missing branches**

In `memory.py`, inside the loop in `format_patch_result`, add before the `add_item` branch:

```python
        elif op.op == "set_due":
            parts.append(f"set_due({op.id}, {op.value})")
        elif op.op == "set_recurs":
            parts.append(f"set_recurs({op.id}, {op.value})")
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_memory.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add memory.py tests/test_memory.py
git commit -m "fix: format_patch_result drops set_due and set_recurs ops"
```

---

### Task 3: `session.py` — item loading and the query path

Establishes the module, the shared `load_items` loader, the outcome dataclasses, and the thread mechanics for text replies.

**Files:**
- Create: `session.py`
- Modify: `pyproject.toml` (add `session` to `py-modules`)
- Test: `tests/test_session.py` (create)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `session.load_items(yaml_path: str) -> list`
  - `session.TextReply(text: str)` — frozen dataclass
  - `session.PatchProposal(ops: list, diffs: list[str], request: str)` — frozen dataclass
  - `session.ValidationFailure(errors: list[str])` — frozen dataclass
  - `session.MAX_THREAD_MESSAGES: int` (= 20)
  - `session.Session(yaml_path: str, adapter)` with `.items`, `.thread`, `.start() -> list`, `.submit(text: str) -> TextReply | PatchProposal | ValidationFailure`

- [ ] **Step 1: Write the failing test**

Create `tests/test_session.py`:

```python
from unittest.mock import MagicMock

import pytest

from patch import PatchOp
from session import Session, TextReply, load_items


class FakeAdapter:
    """Adapter stub returning canned results and recording what it was sent."""

    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def complete_messages(self, system, messages):
        self.calls.append({"system": system, "messages": messages})
        return self.results.pop(0)


@pytest.fixture
def session(sample_yaml_file):
    adapter = FakeAdapter([])
    return Session(str(sample_yaml_file), adapter)


def test_load_items_reads_the_file(sample_yaml_file):
    items = load_items(str(sample_yaml_file))
    assert {i["id"] for i in items} == {"annual_report", "emsn230", "budget_review"}


def test_start_populates_items(session):
    items = session.start()
    assert len(items) == 3
    assert session.items == items


def test_start_leaves_thread_empty(session):
    session.start()
    assert session.thread == []


def test_submit_query_returns_text_reply(session):
    session.start()
    session.adapter.results = [("Annual Report is in focus.", [], None)]

    result = session.submit("what is in focus?")

    assert isinstance(result, TextReply)
    assert result.text == "Annual Report is in focus."


def test_submit_query_records_both_turns(session):
    session.start()
    session.adapter.results = [("Annual Report is in focus.", [], None)]

    session.submit("what is in focus?")

    assert session.thread == [
        {"role": "user", "content": "what is in focus?"},
        {"role": "assistant", "content": "Annual Report is in focus."},
    ]


def test_thread_stores_naked_user_text_without_yaml(session):
    session.start()
    session.adapter.results = [("ok", [], None)]

    session.submit("what is in focus?")

    assert "annual_report" not in session.thread[0]["content"]


def test_sent_message_carries_the_yaml_snapshot(session):
    session.start()
    session.adapter.results = [("ok", [], None)]

    session.submit("what is in focus?")

    sent = session.adapter.calls[0]["messages"][-1]["content"]
    assert "annual_report" in sent
    assert "what is in focus?" in sent


def test_second_submit_sends_prior_turns_then_fresh_snapshot(session):
    session.start()
    session.adapter.results = [("first", [], None), ("second", [], None)]

    session.submit("one")
    session.submit("two")

    messages = session.adapter.calls[1]["messages"]
    assert messages[0] == {"role": "user", "content": "one"}
    assert messages[1] == {"role": "assistant", "content": "first"}
    assert "annual_report" in messages[2]["content"]
    assert "two" in messages[2]["content"]


def test_only_the_newest_message_holds_a_snapshot(session):
    session.start()
    session.adapter.results = [("first", [], None), ("second", [], None)]

    session.submit("one")
    session.submit("two")

    messages = session.adapter.calls[1]["messages"]
    snapshot_count = sum(1 for m in messages if "annual_report" in m["content"])
    assert snapshot_count == 1


def test_failed_api_call_leaves_thread_untouched(session):
    session.start()
    adapter = MagicMock()
    adapter.complete_messages.side_effect = RuntimeError("network down")
    session.adapter = adapter

    with pytest.raises(RuntimeError):
        session.submit("what is in focus?")

    assert session.thread == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_session.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'session'`

- [ ] **Step 3: Create `session.py`**

```python
"""Frontend-agnostic conversational session over the RRM status file.

Owns the items, the LLM adapter, and the message thread. Contains no
rendering and no user I/O, so a REPL, a TUI, or any other frontend can
drive it through the same four methods.
"""

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from auto_today import auto_promote_today, load_auto_today_date, save_auto_today_date
from patch import PatchOp, apply, validate
from prompts import build_system_prompt, build_user_message
from yaml_utils import backup, diff_items, read_items, write_items

MAX_THREAD_MESSAGES = 20


@dataclass(frozen=True)
class TextReply:
    """A query answered in prose."""

    text: str


@dataclass(frozen=True)
class PatchProposal:
    """A validated patch awaiting the user's decision."""

    ops: list[PatchOp]
    diffs: list[str]
    request: str


@dataclass(frozen=True)
class ValidationFailure:
    """A patch that stayed invalid after the retry."""

    errors: list[str]


def load_items(yaml_path: str) -> list:
    """Read items, promoting due and recurring items to today once per day."""
    items = read_items(yaml_path)
    state_path = str(Path(yaml_path).with_name("rrm-auto-today.txt"))
    today = date.today()

    if load_auto_today_date(state_path) == today.strftime("%Y-%m-%d"):
        return items

    promoted = auto_promote_today(items, today=today)
    if diff_items(items, promoted):
        backup(yaml_path)
        write_items(yaml_path, promoted)
    save_auto_today_date(state_path, today)
    return promoted


class Session:
    def __init__(self, yaml_path: str, adapter):
        self.yaml_path = yaml_path
        self.adapter = adapter
        self.items: list = []
        self.thread: list[dict] = []

    def start(self) -> list:
        """Load items and return them. Does not call the LLM."""
        self.items = load_items(self.yaml_path)
        return self.items

    def submit(self, text: str):
        """Send one user turn. Returns TextReply, PatchProposal, or ValidationFailure."""
        system = build_system_prompt()
        messages = self.thread + [
            {"role": "user", "content": build_user_message(text, self.items)}
        ]
        result, _assistant_content, _tool_use_id = self.adapter.complete_messages(
            system, messages
        )

        if isinstance(result, str):
            self._append(text, result)
            return TextReply(result)

        raise NotImplementedError("patch proposals arrive in Task 4")

    def _append(self, user_text: str, assistant_text: str) -> None:
        """Record one alternating pair and trim to the cap."""
        self.thread.append({"role": "user", "content": user_text})
        self.thread.append({"role": "assistant", "content": assistant_text})
        self._trim()

    def _trim(self) -> None:
        """Drop oldest pairs so the thread stays capped and starts with a user turn."""
        while len(self.thread) > MAX_THREAD_MESSAGES:
            del self.thread[:2]
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_session.py -v`
Expected: PASS, all 10 tests.

- [ ] **Step 5: Add `session` to `pyproject.toml`**

Append `"session"` to the `py-modules` list.

- [ ] **Step 6: Run the full suite**

Run: `uv run pytest`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add session.py pyproject.toml tests/test_session.py
git commit -m "feat: add Session core with query path and message thread"
```

---

### Task 4: `session.py` — patch proposals and the internal validation retry

**Files:**
- Modify: `session.py` (replace the `NotImplementedError` branch)
- Test: `tests/test_session.py`

**Interfaces:**
- Consumes: `Session`, `PatchProposal`, `ValidationFailure`, `TextReply` from Task 3.
- Produces: `Session.submit` returning `PatchProposal(ops, diffs, request)` for valid patches and `ValidationFailure(errors)` for patches still invalid after one retry. Neither appends to the thread — Task 5's `accept`/`decline` does that for proposals.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_session.py`:

```python
from session import PatchProposal, ValidationFailure


def test_submit_valid_patch_returns_proposal(session):
    session.start()
    ops = [PatchOp(op="set_status", id="emsn230", value="waiting")]
    session.adapter.results = [(ops, [], None)]

    result = session.submit("put Sri Lanka on waiting")

    assert isinstance(result, PatchProposal)
    assert result.ops == ops
    assert result.request == "put Sri Lanka on waiting"
    assert any("emsn230" in d for d in result.diffs)


def test_proposal_does_not_touch_the_thread(session):
    session.start()
    ops = [PatchOp(op="set_status", id="emsn230", value="waiting")]
    session.adapter.results = [(ops, [], None)]

    session.submit("put Sri Lanka on waiting")

    assert session.thread == []


def test_proposal_does_not_write_the_file(session, sample_yaml_file):
    session.start()
    before = sample_yaml_file.read_text()
    ops = [PatchOp(op="set_status", id="emsn230", value="waiting")]
    session.adapter.results = [(ops, [], None)]

    session.submit("put Sri Lanka on waiting")

    assert sample_yaml_file.read_text() == before


def test_invalid_patch_is_retried_once(session):
    session.start()
    bad = [PatchOp(op="set_status", id="nonexistent", value="waiting")]
    good = [PatchOp(op="set_status", id="emsn230", value="waiting")]
    session.adapter.results = [(bad, [], "tool_1"), (good, [], "tool_2")]

    result = session.submit("put Sri Lanka on waiting")

    assert isinstance(result, PatchProposal)
    assert result.ops == good
    assert len(session.adapter.calls) == 2


def test_retry_sends_the_errors_as_a_tool_result(session):
    session.start()
    bad = [PatchOp(op="set_status", id="nonexistent", value="waiting")]
    good = [PatchOp(op="set_status", id="emsn230", value="waiting")]
    session.adapter.results = [(bad, [], "tool_1"), (good, [], "tool_2")]

    session.submit("put Sri Lanka on waiting")

    retry_messages = session.adapter.calls[1]["messages"]
    tool_result = retry_messages[-1]["content"][0]
    assert tool_result["type"] == "tool_result"
    assert tool_result["tool_use_id"] == "tool_1"
    assert tool_result["is_error"] is True
    assert "nonexistent" in tool_result["content"]


def test_retry_answering_in_text_returns_a_text_reply(session):
    session.start()
    bad = [PatchOp(op="set_status", id="nonexistent", value="waiting")]
    session.adapter.results = [
        (bad, [], "tool_1"),
        ("There is no item with that id.", [], None),
    ]

    result = session.submit("mark the thing done")

    assert isinstance(result, TextReply)
    assert result.text == "There is no item with that id."
    assert session.thread[-1]["content"] == "There is no item with that id."


def test_still_invalid_after_retry_returns_validation_failure(session):
    session.start()
    bad = [PatchOp(op="set_status", id="nonexistent", value="waiting")]
    session.adapter.results = [(bad, [], "tool_1"), (bad, [], "tool_2")]

    result = session.submit("change something")

    assert isinstance(result, ValidationFailure)
    assert any("nonexistent" in e for e in result.errors)
    assert session.thread == []


def test_invalid_patch_without_tool_use_id_is_not_retried(session):
    session.start()
    bad = [PatchOp(op="set_status", id="nonexistent", value="waiting")]
    session.adapter.results = [(bad, [], None)]

    result = session.submit("change something")

    assert isinstance(result, ValidationFailure)
    assert len(session.adapter.calls) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_session.py -v -k "proposal or retry"`
Expected: FAIL with `NotImplementedError: patch proposals arrive in Task 4`

- [ ] **Step 3: Replace the `NotImplementedError` branch**

In `session.py`, replace the `raise NotImplementedError(...)` line with:

```python
        ops = result
        errors = validate(ops, self.items)

        if errors and _tool_use_id is not None:
            retried = self._retry(system, messages, _assistant_content, _tool_use_id, errors)
            result, _assistant_content, _tool_use_id = retried
            if isinstance(result, str):
                self._append(text, result)
                return TextReply(result)
            ops = result
            errors = validate(ops, self.items)

        if errors:
            return ValidationFailure(errors)

        new_items = apply(ops, self.items)
        return PatchProposal(ops=ops, diffs=diff_items(self.items, new_items), request=text)
```

Rename the two locals from `_assistant_content` / `_tool_use_id` to `assistant_content` / `tool_use_id` throughout `submit` now that they are used.

Add the retry helper to the class:

```python
    def _retry(self, system: str, messages: list[dict], assistant_content, tool_use_id: str, errors: list[str]):
        """Feed validation errors back as a tool_result and ask once more.

        These turns are deliberately local: only the final outcome reaches
        the thread, so a rejected proposal never becomes conversation.
        """
        error_text = "Validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
        retry_messages = messages + [
            {"role": "assistant", "content": assistant_content},
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": error_text,
                        "is_error": True,
                    }
                ],
            },
        ]
        return self.adapter.complete_messages(system, retry_messages)
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_session.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add session.py tests/test_session.py
git commit -m "feat: Session proposes validated patches with an internal retry"
```

---

### Task 5: `session.py` — accept, decline, and outcome recording

**Files:**
- Modify: `session.py`
- Test: `tests/test_session.py`

**Interfaces:**
- Consumes: `PatchProposal` from Task 4, `memory.format_patch_result` from Task 2.
- Produces:
  - `Session.accept(proposal: PatchProposal) -> list` — writes YAML, refreshes `self.items`, returns them
  - `Session.decline(proposal: PatchProposal) -> None`
  - `session.APPLIED_NOTE: str`, `session.DECLINED_NOTE: str`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_session.py`:

```python
import json
from pathlib import Path

from memory import history_path
from session import APPLIED_NOTE, DECLINED_NOTE
from yaml_utils import read_items


def _propose(session, ops, request="change it"):
    session.adapter.results = [(ops, [], None)]
    return session.submit(request)


def test_accept_writes_the_file(session, sample_yaml_file):
    session.start()
    proposal = _propose(session, [PatchOp(op="set_status", id="emsn230", value="waiting")])

    session.accept(proposal)

    items = read_items(str(sample_yaml_file))
    assert next(i for i in items if i["id"] == "emsn230")["status"] == "waiting"


def test_accept_refreshes_items_and_returns_them(session):
    session.start()
    proposal = _propose(session, [PatchOp(op="set_status", id="emsn230", value="waiting")])

    returned = session.accept(proposal)

    assert next(i for i in returned if i["id"] == "emsn230")["status"] == "waiting"
    assert session.items == returned


def test_accept_creates_a_backup(session, sample_yaml_file):
    session.start()
    proposal = _propose(session, [PatchOp(op="set_status", id="emsn230", value="waiting")])

    session.accept(proposal)

    assert Path(str(sample_yaml_file) + ".bak").exists()


def test_accept_records_an_alternating_pair(session):
    session.start()
    proposal = _propose(session, [PatchOp(op="set_status", id="emsn230", value="waiting")], "put it on waiting")

    session.accept(proposal)

    assert len(session.thread) == 2
    assert session.thread[0] == {"role": "user", "content": "put it on waiting"}
    assert session.thread[1]["role"] == "assistant"
    assert "set_status(emsn230, waiting)" in session.thread[1]["content"]
    assert APPLIED_NOTE in session.thread[1]["content"]


def test_accept_appends_to_history_file(session, sample_yaml_file):
    session.start()
    proposal = _propose(session, [PatchOp(op="set_status", id="emsn230", value="waiting")], "put it on waiting")

    session.accept(proposal)

    data = json.loads(Path(history_path(str(sample_yaml_file))).read_text())
    assert data[-1]["request"] == "put it on waiting"
    assert "emsn230" in data[-1]["result"]


def test_decline_leaves_the_file_byte_identical(session, sample_yaml_file):
    session.start()
    before = sample_yaml_file.read_text()
    proposal = _propose(session, [PatchOp(op="set_status", id="emsn230", value="waiting")])

    session.decline(proposal)

    assert sample_yaml_file.read_text() == before


def test_decline_records_the_rejection_explicitly(session):
    session.start()
    proposal = _propose(session, [PatchOp(op="set_status", id="emsn230", value="waiting")], "put it on waiting")

    session.decline(proposal)

    assert session.thread[1]["role"] == "assistant"
    assert DECLINED_NOTE in session.thread[1]["content"]
    assert "set_status(emsn230, waiting)" in session.thread[1]["content"]


def test_decline_writes_no_history(session, sample_yaml_file):
    session.start()
    proposal = _propose(session, [PatchOp(op="set_status", id="emsn230", value="waiting")])

    session.decline(proposal)

    assert not Path(history_path(str(sample_yaml_file))).exists()


def test_thread_alternates_after_mixed_turns(session):
    session.start()
    session.adapter.results = [("a text answer", [], None)]
    session.submit("a question")
    proposal = _propose(session, [PatchOp(op="set_status", id="emsn230", value="waiting")])
    session.accept(proposal)

    roles = [m["role"] for m in session.thread]
    assert roles == ["user", "assistant", "user", "assistant"]


def test_thread_trims_to_the_cap_oldest_pair_first(session):
    session.start()
    for n in range(12):
        session.adapter.results = [(f"answer {n}", [], None)]
        session.submit(f"question {n}")

    assert len(session.thread) == 20
    assert session.thread[0] == {"role": "user", "content": "question 2"}
    assert session.thread[0]["role"] == "user"
```

Retry turns must also stay out of the thread once a proposal is accepted:

```python
def test_retry_turns_stay_out_of_the_thread(session):
    session.start()
    bad = [PatchOp(op="set_status", id="nonexistent", value="waiting")]
    good = [PatchOp(op="set_status", id="emsn230", value="waiting")]
    session.adapter.results = [(bad, [], "tool_1"), (good, [], "tool_2")]

    proposal = session.submit("put Sri Lanka on waiting")
    session.accept(proposal)

    assert len(session.thread) == 2
    assert all("tool_result" not in str(m["content"]) for m in session.thread)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_session.py -v -k "accept or decline"`
Expected: FAIL with `ImportError: cannot import name 'APPLIED_NOTE'`

- [ ] **Step 3: Implement accept and decline**

Add the notes near `MAX_THREAD_MESSAGES` in `session.py`:

```python
APPLIED_NOTE = "[Applied to the status file.]"
DECLINED_NOTE = "[NOT applied - the user declined this patch. The state is unchanged.]"
```

Extend the imports:

```python
from memory import format_patch_result, history_path, load_history, save_history
```

Add the two methods to `Session`:

```python
    def accept(self, proposal: PatchProposal) -> list:
        """Write the patch, refresh items, and record the applied turn."""
        new_items = apply(proposal.ops, self.items)
        backup(self.yaml_path)
        write_items(self.yaml_path, new_items)
        self.items = read_items(self.yaml_path)

        summary = format_patch_result(proposal.ops)
        self._append(proposal.request, f"{summary}\n\n{APPLIED_NOTE}")

        path = history_path(self.yaml_path)
        save_history(path, load_history(path), proposal.request, summary)
        return self.items

    def decline(self, proposal: PatchProposal) -> None:
        """Record that the patch was rejected. Nothing is written."""
        summary = format_patch_result(proposal.ops)
        self._append(proposal.request, f"{summary}\n\n{DECLINED_NOTE}")
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_session.py -v`
Expected: PASS

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add session.py tests/test_session.py
git commit -m "feat: Session accept and decline with explicit outcome turns"
```

---

### Task 6: Remove the confirmation workaround from `prompts.py`

The `Confirmation handling` block tells the model to treat "yes" as confirming a pending change. It existed because there was no thread. In a session, `Apply? [Y/n]` is handled in Python and never reaches the LLM, so the block would let a bare "yes" be reinterpreted as re-applying something.

**Files:**
- Modify: `prompts.py:55-61`
- Test: `tests/test_prompts.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `build_system_prompt()` unchanged in signature.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_prompts.py`:

```python
def test_system_prompt_has_no_affirmation_shortcut():
    prompt = build_system_prompt()
    assert "Confirmation handling" not in prompt
    assert "short affirmation" not in prompt
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_prompts.py -v -k affirmation`
Expected: FAIL — the string is present.

- [ ] **Step 3: Delete the block**

From `SYSTEM_PROMPT` in `prompts.py`, remove these seven lines in full:

```text
Confirmation handling
- If the user's message is a short affirmation ("yes", "y", "1", "ok",
  "correct", "do it") and the recent history shows a pending proposed
  change, treat it as confirmation and apply that change immediately.
- Do not re-ask for confirmation of something you already asked about.
```

Leave the blank line structure intact so `Identification` is followed directly by `Patch discipline`.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_prompts.py -v`
Expected: PASS. If another test asserts on the removed text, update it.

- [ ] **Step 5: Commit**

```bash
git add prompts.py tests/test_prompts.py
git commit -m "refactor: drop the affirmation confirmation workaround from the prompt"
```

---

### Task 7: `repl.py` — command parsing

The dispatch layer, built and tested before the interactive loop wraps it.

**Files:**
- Create: `repl.py`
- Modify: `pyproject.toml` (add `repl` to `py-modules`)
- Test: `tests/test_repl.py` (create)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `repl.COMMANDS: dict[str, str]` — command name to help text
  - `repl.parse_input(text: str) -> tuple[str, str]` returning one of `("empty", "")`, `("command", "/status")`, `("unknown", "/foo")`, `("llm", "<text>")`

- [ ] **Step 1: Write the failing test**

Create `tests/test_repl.py`:

```python
import pytest

from repl import COMMANDS, parse_input


def test_blank_input_is_empty():
    assert parse_input("") == ("empty", "")
    assert parse_input("   ") == ("empty", "")


@pytest.mark.parametrize("name", ["/status", "/brief", "/archive", "/help", "/quit"])
def test_known_commands_are_recognised(name):
    assert parse_input(name) == ("command", name)


def test_commands_tolerate_surrounding_whitespace():
    assert parse_input("  /status  ") == ("command", "/status")


def test_unknown_slash_command_is_not_sent_to_the_llm():
    assert parse_input("/nope") == ("unknown", "/nope")


def test_plain_text_goes_to_the_llm():
    assert parse_input("what is in focus?") == ("llm", "what is in focus?")


def test_text_containing_status_is_not_a_command():
    assert parse_input("status of emsn230?") == ("llm", "status of emsn230?")


def test_command_with_trailing_words_is_unknown():
    assert parse_input("/brief me on emsn230") == ("unknown", "/brief me on emsn230")


def test_every_command_has_help_text():
    assert set(COMMANDS) == {"/status", "/brief", "/archive", "/help", "/quit"}
    assert all(COMMANDS.values())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_repl.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'repl'`

- [ ] **Step 3: Create `repl.py` with the parser**

```python
"""Terminal frontend for the interactive session.

Owns input, rendering, and command dispatch. Knows nothing about the
Anthropic API or patch validation - that all lives in session.py.
"""

COMMANDS = {
    "/status": "Reprint the current item list",
    "/brief": "Ask for the daily operational picture",
    "/archive": "Move finished items to the archive",
    "/help": "Show this list",
    "/quit": "Exit the session",
}


def parse_input(text: str) -> tuple[str, str]:
    """Classify one line of input.

    Returns (kind, payload) where kind is empty, command, unknown, or llm.
    A leading slash always means a command, so a typo never costs an API call.
    """
    stripped = text.strip()
    if not stripped:
        return ("empty", "")
    if stripped.startswith("/"):
        if stripped in COMMANDS:
            return ("command", stripped)
        return ("unknown", stripped)
    return ("llm", stripped)
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_repl.py -v`
Expected: PASS

- [ ] **Step 5: Add `repl` to `pyproject.toml`**

Append `"repl"` to the `py-modules` list.

- [ ] **Step 6: Commit**

```bash
git add repl.py pyproject.toml tests/test_repl.py
git commit -m "feat: add REPL command parsing"
```

---

### Task 8: The interactive loop and CLI wiring

Wires `prompt_toolkit` and `rich` around the session, adds `--brief`, and makes bare `rrm-ai` launch the REPL.

**Files:**
- Modify: `repl.py` (add `run`, `handle_command`, rendering helpers)
- Modify: `rrm_ai.py` (`--brief` flag, bare invocation launches the REPL, use `session.load_items`)
- Modify: `pyproject.toml` (add `prompt_toolkit` dependency)
- Modify: `README.md`
- Test: `tests/test_repl.py`, `tests/test_rrm_ai.py`

**Interfaces:**
- Consumes: `session.Session`, `session.load_items`, `session.TextReply`, `session.PatchProposal`, `session.ValidationFailure` (Tasks 3-5); `repl.parse_input`, `repl.COMMANDS` (Task 7); `render.print_status` (Task 1).
- Produces: `repl.run(session, console=None) -> None`, `repl.handle_command(name, session, console) -> bool` (returns False to exit the loop).

- [ ] **Step 1: Add the dependency**

Run: `uv add prompt_toolkit`
Expected: `pyproject.toml` gains `prompt_toolkit` under `dependencies` and `uv.lock` updates.

- [ ] **Step 2: Write the failing test**

Append to `tests/test_repl.py`:

```python
from unittest.mock import MagicMock

from rich.console import Console

from patch import PatchOp
from repl import handle_command
from session import PatchProposal, TextReply, ValidationFailure


def _console():
    return Console(force_terminal=False)


def test_status_command_renders_without_calling_the_llm(capsys):
    session = MagicMock()
    session.items = [{"id": "emsn230", "item": "Activation", "status": "waiting",
                      "today": False, "next_action": "wait"}]

    keep_going = handle_command("/status", session, _console())

    assert keep_going is True
    session.submit.assert_not_called()
    assert "emsn230" in capsys.readouterr().out


def test_help_command_lists_every_command(capsys):
    handle_command("/help", MagicMock(), _console())
    output = capsys.readouterr().out
    for name in ["/status", "/brief", "/archive", "/help", "/quit"]:
        assert name in output


def test_quit_command_stops_the_loop():
    assert handle_command("/quit", MagicMock(), _console()) is False


def test_brief_command_calls_the_llm(capsys):
    session = MagicMock()
    session.submit.return_value = TextReply("## Operational Picture")

    handle_command("/brief", session, _console())

    session.submit.assert_called_once()
    assert "Operational Picture" in capsys.readouterr().out
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_repl.py -v -k command`
Expected: FAIL with `ImportError: cannot import name 'handle_command'`

- [ ] **Step 4: Implement the frontend**

Append to `repl.py`:

```python
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from rich.console import Console
from rich.markdown import Markdown
from rich.theme import Theme

from daily_brief import build_daily_brief_prompt
from render import print_status
from session import PatchProposal, TextReply, ValidationFailure
from theme import LLM_MARKDOWN_THEME, THEME
from yaml_utils import archive_finished, backup

PROMPT = "rrm> "


def _print_markdown(text: str, console: Console) -> None:
    console.push_theme(Theme(LLM_MARKDOWN_THEME))
    console.print(Markdown(text))
    console.pop_theme()


def _print_diffs(diffs: list[str], console: Console) -> None:
    console.print(f"[{THEME['diff_header']}]Proposed changes:[/]")
    for d in diffs:
        style = THEME["diff_add"] if d.strip().startswith("+") else THEME["diff_change"]
        console.print(f"  [{style}]•{d}[/]")


def handle_command(name: str, session, console: Console) -> bool:
    """Run one slash command. Returns False when the loop should stop."""
    if name == "/quit":
        return False
    if name == "/status":
        print_status(session.items, console=console)
    elif name == "/help":
        for command, description in COMMANDS.items():
            console.print(f"  [{THEME['item_id']}]{command}[/]  {description}")
    elif name == "/archive":
        archive_path = str(Path(session.yaml_path).with_name("rrm-archive.yaml"))
        backup(session.yaml_path)
        if Path(archive_path).exists():
            backup(archive_path)
        archive_finished(session.yaml_path, archive_path)
        session.start()
        console.print(f"[{THEME['success']}]Finished items archived.[/]")
        print_status(session.items, console=console)
    elif name == "/brief":
        result = session.submit(build_daily_brief_prompt())
        if isinstance(result, TextReply):
            _print_markdown(result.text, console)
    return True


def _handle_proposal(proposal: PatchProposal, session, console: Console) -> None:
    _print_diffs(proposal.diffs, console)
    answer = input("\nApply? [Y/n] ").strip().lower()
    if answer in ("", "y"):
        session.accept(proposal)
        console.print(f"[{THEME['success']}]Applied.[/]")
        print_status(session.items, console=console)
    else:
        session.decline(proposal)
        console.print(f"[{THEME['aborted']}]Declined.[/]")


def run(session, console: Console | None = None) -> None:
    """Drive the session until the user quits."""
    if console is None:
        console = Console()

    session.start()
    print_status(session.items, console=console)
    console.print(f"[{THEME['aborted']}]Type /help for commands.[/]")

    prompt_session = PromptSession()

    while True:
        try:
            raw = prompt_session.prompt(
                PROMPT,
                completer=WordCompleter(
                    list(COMMANDS) + [i["id"] for i in session.items]
                ),
            )
        except KeyboardInterrupt:
            continue
        except EOFError:
            break

        kind, payload = parse_input(raw)

        if kind == "empty":
            continue
        if kind == "unknown":
            console.print(f"[{THEME['error_line']}]unknown command: {payload}[/]")
            continue
        if kind == "command":
            if not handle_command(payload, session, console):
                break
            continue

        try:
            with console.status("thinking..."):
                result = session.submit(payload)
        except KeyboardInterrupt:
            console.print(f"[{THEME['aborted']}]Cancelled.[/]")
            continue
        except Exception as exc:
            console.print(f"[{THEME['error_line']}]{type(exc).__name__}: {exc}[/]")
            continue

        if isinstance(result, TextReply):
            _print_markdown(result.text, console)
        elif isinstance(result, ValidationFailure):
            console.print(f"[{THEME['error_header']}]Validation errors:[/]")
            for e in result.errors:
                console.print(f"  [{THEME['error_line']}]✗ {e}[/]")
        elif isinstance(result, PatchProposal):
            _handle_proposal(result, session, console)
```

`handle_command` uses `Path`, so add `from pathlib import Path` to the module
imports at the top of `repl.py`.

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/test_repl.py -v`
Expected: PASS

- [ ] **Step 6: Write the failing CLI test**

Append to `tests/test_rrm_ai.py`:

```python
class TestBriefFlag:
    def test_brief_flag_prints_the_daily_picture(self, yaml_env, capsys):
        mock_adapter = MagicMock()
        mock_adapter.complete_messages.return_value = ("## Operational Picture", [], None)

        with patch("sys.argv", ["rrm-ai", "--brief"]):
            with patch("rrm_ai.get_adapter", return_value=mock_adapter):
                main()

        assert "Operational Picture" in capsys.readouterr().out

    def test_brief_flag_does_not_start_the_repl(self, yaml_env):
        mock_adapter = MagicMock()
        mock_adapter.complete_messages.return_value = ("## Operational Picture", [], None)

        with patch("sys.argv", ["rrm-ai", "--brief"]):
            with patch("rrm_ai.get_adapter", return_value=mock_adapter):
                with patch("repl.run") as mock_run:
                    main()
                    mock_run.assert_not_called()


class TestBareInvocation:
    def test_bare_invocation_starts_the_repl(self, yaml_env):
        with patch("sys.argv", ["rrm-ai"]):
            with patch("repl.run") as mock_run:
                main()
                mock_run.assert_called_once()
```

- [ ] **Step 7: Run test to verify it fails**

Run: `uv run pytest tests/test_rrm_ai.py -v -k "Brief or Bare"`
Expected: FAIL — `--brief` is an unrecognized argument.

- [ ] **Step 8: Wire `rrm_ai.py`**

Add the flag next to the others in `main()`:

```python
    parser.add_argument(
        "--brief", action="store_true", help="Print the daily operational picture and exit"
    )
```

Replace the existing daily-brief branch:

```python
    daily_brief = not args.text
    if daily_brief:
        args.text = build_daily_brief_prompt()
```

with:

```python
    if not args.text and not args.brief:
        import repl

        session = Session(yaml_path, get_adapter(config))
        repl.run(session)
        return

    daily_brief = args.brief
    if daily_brief:
        args.text = build_daily_brief_prompt()
```

`config` and `yaml_path` are already set by the `args.status or args.archive`
block above, so this branch reuses them rather than reloading.

Add to the imports:

```python
from session import Session, load_items
```

Then replace the inline promotion block in `main()` — the `auto_today_state`, `already_promoted_today`, and `maybe_promote` definitions and both `items = maybe_promote(items)` calls — with `load_items`:

```python
    if args.status:
        print_status(load_items(yaml_path), console=console)
        return
```

and further down:

```python
    items = load_items(yaml_path)
```

Delete the now-unused `auto_today` imports and the `from datetime import date as _date` line from `rrm_ai.py`.

- [ ] **Step 9: Run the full suite**

Run: `uv run pytest`
Expected: PASS, every test green.

- [ ] **Step 10: Install and smoke test by hand**

```bash
uv tool install --reinstall --editable .
rrm-ai --status
rrm-ai --brief
rrm-ai
```

Expected: `--status` prints the list instantly. `--brief` prints the picture and exits. Bare `rrm-ai` prints the list then shows the `rrm> ` prompt. In the session, check by hand: `/help`, `/status`, `/nope` (prints unknown command, no API call), a question, a change followed by `n`, the same change followed by `y`, arrow-up recall, `/` completion, `Ctrl-C` at the prompt, `/quit`.

- [ ] **Step 11: Update `README.md`**

Under `## Usage`, after the `--status` section, add:

````markdown
Start an interactive session:

```bash
rrm-ai
```

The session prints the current list, then gives you a prompt. Type plain
English to ask or to request changes; the conversation is remembered until
you quit. Commands start with a slash:

| Command | Effect |
| --- | --- |
| `/status` | Reprint the current list |
| `/brief` | Daily operational picture |
| `/archive` | Move finished items to the archive |
| `/help` | List commands |
| `/quit` | Exit (`Ctrl-D` works too) |
````

In the `Useful flags` block, add:

```bash
rrm-ai --brief
```

- [ ] **Step 12: Commit**

```bash
git add repl.py rrm_ai.py pyproject.toml uv.lock README.md tests/test_repl.py tests/test_rrm_ai.py
git commit -m "feat: interactive session as the default rrm-ai invocation"
```

---

## Verification

After Task 8, the whole spec is implemented. Confirm:

- `uv run pytest` is fully green
- Bare `rrm-ai` opens a session; `rrm-ai "text"`, `--status`, `--archive`, `--dry-run`, `--yes` behave as before
- `--brief` reproduces the old bare-invocation output
