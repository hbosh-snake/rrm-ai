from dataclasses import dataclass
import copy
import re
from datetime import date as _date


VALID_STATUSES = {"in_progress", "waiting", "finished"}
VALID_RECURS = {"weekly_fri", "monthly_1", "monthly_last"}
MAX_TODAY = 3


@dataclass
class PatchOp:
    op: str
    id: str
    value: object = None
    item: str | None = None
    status: str | None = None
    today: object = None
    next_action: str | None = None
    due: object = None
    recurs: object = None


def _validate_due(value: object) -> str | None:
    """Return error string if value is not a valid YYYY-MM-DD date string, else None."""
    if not isinstance(value, str):
        return f"due: value must be a string (YYYY-MM-DD), got {type(value).__name__}"
    if not re.match(r'^\d{4}-\d{2}-\d{2}$', value):
        return f"due: invalid date format '{value}' (must be YYYY-MM-DD)"
    try:
        _date.fromisoformat(value)
    except ValueError:
        return f"due: invalid calendar date '{value}'"
    return None


def validate(ops: list[PatchOp], items: list) -> list[str]:
    errors = []
    existing_ids = {item["id"] for item in items}
    items_by_id = {item["id"]: item for item in items}
    known_ops = {
        "set_status",
        "set_today",
        "set_next_action",
        "set_due",
        "set_recurs",
        "add_item",
    }

    # Count current today=True items
    today_count = sum(1 for item in items if item.get("today") is True)  # noqa: F841

    # Track today changes from ops to compute final count
    today_changes: dict[str, bool] = {}

    # Track effective recurs and status per id for cross-field invariant
    effective_recurs: dict[str, object] = {}
    effective_status: dict[str, object] = {}

    for op in ops:
        op_id = op.id

        if op.op not in known_ops:
            errors.append(f"unknown operation '{op.op}'")
            continue

        # ID existence check for mutation ops on existing items
        if op.op in ("set_status", "set_today", "set_next_action", "set_due", "set_recurs"):
            if op_id not in existing_ids:
                errors.append(f"{op.op}: id '{op_id}' not found")

        # Lazily initialise effective state for this id
        if op_id not in effective_recurs:
            orig = items_by_id.get(op_id)
            effective_recurs[op_id] = orig.get("recurs") if orig else None
        if op_id not in effective_status:
            orig = items_by_id.get(op_id)
            effective_status[op_id] = orig.get("status") if orig else None

        if op.op == "set_status":
            if op.value not in VALID_STATUSES:
                errors.append(f"set_status: invalid status '{op.value}' (must be one of {VALID_STATUSES})")
            else:
                effective_status[op_id] = op.value

        elif op.op == "set_today":
            if not isinstance(op.value, bool):
                errors.append(f"set_today: value must be bool, got {type(op.value).__name__}")
            else:
                today_changes[op_id] = op.value

        elif op.op == "set_next_action":
            if not isinstance(op.value, str) or not op.value.strip():
                errors.append("set_next_action: value must be a non-empty string")

        elif op.op == "set_due":
            if op.value is not None:
                err = _validate_due(op.value)
                if err:
                    errors.append(err)

        elif op.op == "set_recurs":
            if op.value is not None:
                if op.value not in VALID_RECURS:
                    errors.append(
                        f"set_recurs: invalid value '{op.value}' (must be one of {VALID_RECURS} or null)"
                    )
                else:
                    effective_recurs[op_id] = op.value
            else:
                effective_recurs[op_id] = None

        elif op.op == "add_item":
            if op_id in existing_ids:
                errors.append(f"add_item: id '{op_id}' already exists")
            if not isinstance(op.item, str) or not op.item.strip():
                errors.append("add_item: item must be a non-empty string")
            if op.status not in VALID_STATUSES:
                errors.append(f"add_item: invalid status '{op.status}'")
            if not isinstance(op.today, bool):
                errors.append(f"add_item: today must be bool, got {type(op.today).__name__}")
            else:
                today_changes[op_id] = op.today
            if not isinstance(op.next_action, str) or not op.next_action.strip():
                errors.append("add_item: next_action must be a non-empty string")
            if op.due is not None:
                err = _validate_due(op.due)
                if err:
                    errors.append(err)
            if op.recurs is not None:
                if op.recurs not in VALID_RECURS:
                    errors.append(
                        f"add_item: invalid recurs '{op.recurs}' (must be one of {VALID_RECURS})"
                    )
                else:
                    effective_recurs[op_id] = op.recurs
            effective_status[op_id] = op.status

    # Compute final today count
    if today_changes:
        final_today = sum(
            1 for item in items
            if item["id"] not in today_changes and item.get("today") is True
        )
        final_today += sum(1 for v in today_changes.values() if v is True)

        if final_today > MAX_TODAY:
            errors.append(f"today: would result in {final_today} items with today=true (max {MAX_TODAY})")

    # Cross-field invariant: recurs + finished are incompatible
    for item_id, r in effective_recurs.items():
        s = effective_status.get(item_id)
        if r and s == "finished":
            errors.append(
                f"invariant: '{item_id}' cannot have recurs='{r}' and status='finished'"
            )

    return errors


def apply(ops: list[PatchOp], items: list) -> list:
    result = copy.deepcopy(items)
    items_by_id = {item["id"]: item for item in result}

    for op in ops:
        if op.op == "set_status":
            items_by_id[op.id]["status"] = op.value
        elif op.op == "set_today":
            if op.value is True:
                items_by_id[op.id]["today"] = True
            else:
                items_by_id[op.id].pop("today", None)
        elif op.op == "set_next_action":
            items_by_id[op.id]["next_action"] = op.value
        elif op.op == "set_due":
            if op.value is None:
                items_by_id[op.id].pop("due", None)
            else:
                items_by_id[op.id]["due"] = op.value
        elif op.op == "set_recurs":
            if op.value is None:
                items_by_id[op.id].pop("recurs", None)
            else:
                items_by_id[op.id]["recurs"] = op.value
        elif op.op == "add_item":
            new_item = {
                "id": op.id,
                "item": op.item,
                "status": op.status,
                "today": op.today,
            }
            if op.due is not None:
                new_item["due"] = op.due
            if op.recurs is not None:
                new_item["recurs"] = op.recurs
            new_item["next_action"] = op.next_action
            result.append(new_item)

    return result
