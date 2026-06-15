import json
from pathlib import Path

from patch import PatchOp

MAX_ENTRIES = 5


def history_path(yaml_path: str) -> str:
    return str(Path(yaml_path).with_name("rrm-history.json"))


def load_history(path: str) -> list[dict]:
    p = Path(path)
    if not p.exists():
        return []
    try:
        with p.open() as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def save_history(path: str, history: list[dict], request: str, result: str) -> None:
    updated = (history + [{"request": request, "result": result}])[-MAX_ENTRIES:]
    with open(path, "w") as f:
        json.dump(updated, f, indent=2)


def format_patch_result(ops: list[PatchOp]) -> str:
    parts = []
    for op in ops:
        if op.op == "set_status":
            parts.append(f"set_status({op.id}, {op.value})")
        elif op.op == "set_today":
            parts.append(f"set_today({op.id}, {op.value})")
        elif op.op == "set_next_action":
            parts.append(f"set_next_action({op.id})")
        elif op.op == "add_item":
            parts.append(f"add_item({op.id})")
    return ", ".join(parts)
