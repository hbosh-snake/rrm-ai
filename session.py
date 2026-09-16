"""Frontend-agnostic conversational session over the RRM status file.

Owns the items, the LLM adapter, and the message thread. Contains no
rendering and no user I/O, so a REPL, a TUI, or any other frontend can
drive it through the same four methods.
"""

from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path

from auto_today import auto_promote_today, load_auto_today_date, save_auto_today_date
from memory import format_patch_result, history_path, load_history, save_history
from patch import PatchOp, apply, validate
from prompts import build_system_prompt, build_user_message
from transcript import log_turn, prune
from yaml_utils import backup, diff_items, read_items, write_items

MAX_THREAD_MESSAGES = 20
APPLIED_RESULT = "Applied to the status file."
DECLINED_RESULT = "NOT applied - the user declined this patch. The state is unchanged."
UNDONE_NOTE = "The last change to the status file was reverted. The current state is authoritative."


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
    tool_use_id: str


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
        self.exchanges: list[list[dict]] = []

    @property
    def thread(self) -> list[dict]:
        """All recorded messages, oldest first."""
        return [m for exchange in self.exchanges for m in exchange]

    def start(self) -> list:
        """Load items and return them. Does not call the LLM."""
        prune(self.yaml_path)
        self.items = load_items(self.yaml_path)
        return self.items

    def submit(self, text: str, brief: bool = False):
        """Send one user turn. Returns TextReply, PatchProposal, or ValidationFailure."""
        system = build_system_prompt()
        messages = self.thread + [
            {"role": "user", "content": build_user_message(text, self.items)}
        ]
        result, assistant_content, tool_use_id = self.adapter.complete_messages(
            system, messages, brief=brief
        )
        retry_errors = None

        if isinstance(result, str):
            self._append(text, result)
            self._log_submit(messages, retry_errors, result_kind="text", response_text=result)
            return TextReply(result)

        ops = result
        errors = validate(ops, self.items)

        if errors and tool_use_id is not None:
            retry_errors = errors
            retry_result = self._retry(system, messages, assistant_content, tool_use_id, errors)
            result, assistant_content, tool_use_id = retry_result
            if isinstance(result, str):
                self._append(text, result)
                self._log_submit(messages, retry_errors, result_kind="text", response_text=result)
                return TextReply(result)
            ops = result
            errors = validate(ops, self.items)

        if errors:
            self._log_submit(messages, retry_errors, result_kind="validation_failure", errors=errors)
            return ValidationFailure(errors)

        new_items = apply(ops, self.items)
        self._log_submit(messages, retry_errors, result_kind="patch_proposal", ops=ops)
        return PatchProposal(
            ops=ops, diffs=diff_items(self.items, new_items), request=text, tool_use_id=tool_use_id
        )

    def accept(self, proposal: PatchProposal) -> list:
        """Write the patch, refresh items, and record the applied turn."""
        new_items = apply(proposal.ops, self.items)
        backup(self.yaml_path)
        write_items(self.yaml_path, new_items)
        self.items = read_items(self.yaml_path)

        self._append_patch(proposal, APPLIED_RESULT)
        self._log_outcome("accept", proposal)

        path = history_path(self.yaml_path)
        save_history(path, load_history(path), proposal.request, format_patch_result(proposal.ops))
        return self.items

    def decline(self, proposal: PatchProposal) -> None:
        """Record that the patch was rejected. Nothing is written."""
        self._append_patch(proposal, DECLINED_RESULT)
        self._log_outcome("decline", proposal)

    def undo_diffs(self) -> list[str] | None:
        """Changes an undo would make, or None when there is no backup."""
        backup_path = Path(self.yaml_path + ".bak")
        if not backup_path.exists():
            return None
        return diff_items(self.items, read_items(str(backup_path)))

    def undo(self) -> list:
        """Swap the status file with its backup, so a second undo redoes."""
        current = Path(self.yaml_path)
        backup_path = Path(self.yaml_path + ".bak")
        swap = Path(self.yaml_path + ".swap")
        current.rename(swap)
        backup_path.rename(current)
        swap.rename(backup_path)
        self.items = read_items(self.yaml_path)
        self._append("/undo", UNDONE_NOTE)
        log_turn(self.yaml_path, {"ts": datetime.now().isoformat(), "kind": "undo"})
        return self.items

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

    def _log_submit(self, messages: list[dict], retry_errors: list[str] | None, result_kind: str, **fields) -> None:
        """Write one debug transcript entry for a submit() call.

        retry_errors holds the first attempt's validation errors when a retry happened.
        """
        if "ops" in fields:
            fields["ops"] = [asdict(op) for op in fields["ops"]]
        entry = {
            "ts": datetime.now().isoformat(),
            "kind": "submit",
            "messages": messages,
            "retried": retry_errors is not None,
            "retry_errors": retry_errors,
            "result_kind": result_kind,
            **fields,
        }
        log_turn(self.yaml_path, entry)

    def _log_outcome(self, kind: str, proposal: PatchProposal) -> None:
        """Write one debug transcript entry for accept() or decline()."""
        log_turn(self.yaml_path, {
            "ts": datetime.now().isoformat(),
            "kind": kind,
            "request": proposal.request,
            "ops": [asdict(op) for op in proposal.ops],
        })

    def _append(self, user_text: str, assistant_text: str) -> None:
        """Record a prose exchange."""
        self._add_exchange([
            {"role": "user", "content": user_text},
            {"role": "assistant", "content": assistant_text},
        ])

    def _append_patch(self, proposal: PatchProposal, outcome: str) -> None:
        """Record a patch exchange as a real tool_use and its tool_result.

        Storing the call as text taught the model to answer with the text
        instead of calling the tool.
        """
        ops = [{k: v for k, v in asdict(op).items() if v is not None} for op in proposal.ops]
        self._add_exchange([
            {"role": "user", "content": proposal.request},
            {"role": "assistant", "content": [{
                "type": "tool_use", "id": proposal.tool_use_id,
                "name": "apply_patch", "input": {"operations": ops},
            }]},
            {"role": "user", "content": [{
                "type": "tool_result", "tool_use_id": proposal.tool_use_id, "content": outcome,
            }]},
        ])

    def _add_exchange(self, messages: list[dict]) -> None:
        """Append one exchange, dropping whole old exchanges to stay under the cap."""
        self.exchanges.append(messages)
        while len(self.thread) > MAX_THREAD_MESSAGES:
            del self.exchanges[0]
