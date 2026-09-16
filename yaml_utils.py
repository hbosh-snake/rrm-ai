import shutil
from io import StringIO
from pathlib import Path

from ruamel.yaml import YAML

VALID_STATUSES = {"in_progress", "waiting", "finished"}


def _make_yaml() -> YAML:
    y = YAML()
    y.default_flow_style = False
    y.preserve_quotes = True
    return y


def read_items(path: str) -> list:
    y = _make_yaml()
    with open(path) as f:
        data = y.load(f)

    items = data if data else []
    invalid = []
    for item in items:
        status = item.get("status")
        if status not in VALID_STATUSES:
            item_id = item.get("id", "<missing id>")
            invalid.append((item_id, status))

    if invalid:
        bad_items = ", ".join(f"{item_id}={status!r}" for item_id, status in invalid)
        allowed = ", ".join(sorted(VALID_STATUSES))
        raise ValueError(
            f"Invalid status value(s) for item id(s): {bad_items}. Allowed values: {allowed}"
        )

    return items


def _normalize_item_spacing(text: str) -> str:
    """Keep one blank line between top-level items and none within an item."""
    lines = text.splitlines()
    normalized = []

    for line in lines:
        if not line.strip():
            continue

        if line.startswith("- ") and normalized and normalized[-1] != "":
            normalized.append("")

        normalized.append(line)

    return "\n".join(normalized) + "\n"


def write_items(path: str, items: list) -> None:
    y = _make_yaml()
    buf = StringIO()
    y.dump(items, buf)
    normalized = _normalize_item_spacing(buf.getvalue())
    with open(path, "w") as f:
        f.write(normalized)


def backup(path: str) -> None:
    shutil.copy2(path, path + ".bak")


def diff_items(old: list, new: list) -> list[str]:
    diffs = []
    old_by_id = {item["id"]: item for item in old}
    new_by_id = {item["id"]: item for item in new}

    for item_id, new_item in new_by_id.items():
        if item_id not in old_by_id:
            diffs.append(f"  + {item_id}  added: {new_item['item']}")
            continue
        old_item = old_by_id[item_id]
        for field in ("status", "today", "due", "recurs", "next_action"):
            old_val = old_item.get(field)
            new_val = new_item.get(field)
            if old_val != new_val:
                diffs.append(f"  {item_id}  {field}: {old_val} \u2192 {new_val}")

    for item_id, old_item in old_by_id.items():
        if item_id not in new_by_id:
            diffs.append(f"  - {item_id}  removed: {old_item['item']}")

    return diffs


def archive_finished(path: str, archive_path: str) -> None:
    items = read_items(path)
    finished = [i for i in items if i["status"] == "finished"]
    remaining = [i for i in items if i["status"] != "finished"]

    if not finished:
        return

    archive_items = []
    archive_file = Path(archive_path)
    if archive_file.exists():
        archive_items = read_items(archive_path)

    archive_items.extend(finished)

    write_items(path, remaining)
    write_items(archive_path, archive_items)
