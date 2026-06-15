import calendar
import copy
from datetime import date
from pathlib import Path

from ruamel.yaml.comments import CommentedMap
from ruamel.yaml.error import CommentMark
from ruamel.yaml.tokens import CommentToken

from patch import MAX_TODAY


def load_auto_today_date(state_path: str) -> str | None:
    p = Path(state_path)
    return p.read_text().strip() if p.exists() else None


def save_auto_today_date(state_path: str, today: date) -> None:
    Path(state_path).write_text(today.strftime("%Y-%m-%d"))


def _set_today_clean(item) -> None:
    """Set today: true without introducing a spurious blank line before the key.

    ruamel.yaml stores inter-item blank lines as a CommentToken on the last
    key of each mapping.  When we append a new key the token stays on the old
    last key, which pushes a blank line *before* the new key.  We move the
    token onto 'today' so the blank line ends up after it instead.
    """
    if not isinstance(item, CommentedMap):
        item["today"] = True
        return

    keys = list(item.keys())
    if keys:
        last_key = keys[-1]
        ca_entry = item.ca.items.get(last_key)
        if ca_entry and ca_entry[2] is not None and ca_entry[2].value == "\n\n":
            old = ca_entry[2]
            ca_entry[2] = CommentToken("\n", old.start_mark, old.end_mark)
            item["today"] = True
            item.ca.items["today"] = [
                None,
                None,
                CommentToken("\n\n", CommentMark(old.start_mark.column), None),
                None,
            ]
            return

    item["today"] = True


def _recurs_fires_today(recurs: str, today: date) -> bool:
    if recurs == "weekly_fri":
        return today.weekday() == 4
    if recurs == "monthly_1":
        return today.day == 1
    if recurs == "monthly_last":
        last = calendar.monthrange(today.year, today.month)[1]
        return today.day == last
    return False


def auto_promote_today(items: list, today: date | None = None) -> list:
    if today is None:
        today = date.today()
    today_str = today.strftime("%Y-%m-%d")

    current_count = sum(1 for item in items if item.get("today") is True)
    if current_count >= MAX_TODAY:
        return items

    result = copy.deepcopy(items)
    for item in result:
        if current_count >= MAX_TODAY:
            break
        if item.get("today") is True:
            continue
        if item.get("status") == "finished":
            continue
        due = item.get("due")
        recurs = item.get("recurs")
        if (due and str(due) == today_str) or (recurs and _recurs_fires_today(recurs, today)):
            _set_today_clean(item)
            current_count += 1

    return result
