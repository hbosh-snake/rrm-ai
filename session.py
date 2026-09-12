"""Frontend-agnostic conversational session over the RRM status file.

Owns the items, the LLM adapter, and the message thread. Contains no
rendering and no user I/O, so a REPL, a TUI, or any other frontend can
drive it through the same four methods.
"""

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from auto_today import auto_promote_today, load_auto_today_date, save_auto_today_date
from memory import format_patch_result, history_path, load_history, save_history
from patch import PatchOp, apply, validate
from prompts import build_system_prompt, build_user_message
from yaml_utils import backup, diff_items, read_items, write_items

MAX_THREAD_MESSAGES = 20
APPLIED_NOTE = "[Applied to the status file.]"
DECLINED_NOTE = "[NOT applied - the user declined this patch. The state is unchanged.]"


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
        result, assistant_content, tool_use_id = self.adapter.complete_messages(
            system, messages
        )

        if isinstance(result, str):
            self._append(text, result)
            return TextReply(result)

        ops = result
        errors = validate(ops, self.items)

        if errors and tool_use_id is not None:
            retried = self._retry(system, messages, assistant_content, tool_use_id, errors)
            result, assistant_content, tool_use_id = retried
            if isinstance(result, str):
                self._append(text, result)
                return TextReply(result)
            ops = result
            errors = validate(ops, self.items)

        if errors:
            return ValidationFailure(errors)

        new_items = apply(ops, self.items)
        return PatchProposal(ops=ops, diffs=diff_items(self.items, new_items), request=text)

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

    def _append(self, user_text: str, assistant_text: str) -> None:
        """Record one alternating pair and trim to the cap."""
        self.thread.append({"role": "user", "content": user_text})
        self.thread.append({"role": "assistant", "content": assistant_text})
        self._trim()

    def _trim(self) -> None:
        """Drop oldest pairs so the thread stays capped and starts with a user turn."""
        while len(self.thread) > MAX_THREAD_MESSAGES:
            del self.thread[:2]
