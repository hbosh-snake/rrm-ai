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
