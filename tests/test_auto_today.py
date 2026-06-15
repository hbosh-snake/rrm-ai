from datetime import date
import calendar

import pytest

from auto_today import auto_promote_today, load_auto_today_date, save_auto_today_date


def _item(id, status="in_progress", today=None, due=None, recurs=None):
    d = {"id": id, "item": f"Item {id}", "status": status, "next_action": "Do something."}
    if today is not None:
        d["today"] = today
    if due is not None:
        d["due"] = due
    if recurs is not None:
        d["recurs"] = recurs
    return d


TODAY = date(2026, 2, 20)  # Friday, 2026-02-20
TODAY_STR = "2026-02-20"

# last day of Feb 2026
LAST_FEB = date(2026, 2, 28)
LAST_FEB_STR = "2026-02-28"


def test_due_today_promotes():
    items = [_item("a", due=TODAY_STR)]
    result = auto_promote_today(items, today=TODAY)
    assert result[0]["today"] is True


def test_due_past_not_promoted():
    items = [_item("a", due="2026-02-19")]
    result = auto_promote_today(items, today=TODAY)
    assert result[0].get("today") is not True


def test_due_future_not_promoted():
    items = [_item("a", due="2026-02-21")]
    result = auto_promote_today(items, today=TODAY)
    assert result[0].get("today") is not True


def test_recurs_weekly_fri_on_friday():
    items = [_item("a", recurs="weekly_fri")]
    result = auto_promote_today(items, today=TODAY)  # TODAY is Friday
    assert result[0]["today"] is True


def test_recurs_weekly_fri_not_friday():
    thursday = date(2026, 2, 19)
    items = [_item("a", recurs="weekly_fri")]
    result = auto_promote_today(items, today=thursday)
    assert result[0].get("today") is not True


def test_recurs_monthly_1_on_first():
    first = date(2026, 2, 1)
    items = [_item("a", recurs="monthly_1")]
    result = auto_promote_today(items, today=first)
    assert result[0]["today"] is True


def test_recurs_monthly_1_not_first():
    items = [_item("a", recurs="monthly_1")]
    result = auto_promote_today(items, today=TODAY)  # 20th
    assert result[0].get("today") is not True


def test_recurs_monthly_last_on_last_day():
    items = [_item("a", recurs="monthly_last")]
    result = auto_promote_today(items, today=LAST_FEB)
    assert result[0]["today"] is True


def test_recurs_monthly_last_not_last_day():
    items = [_item("a", recurs="monthly_last")]
    result = auto_promote_today(items, today=TODAY)  # 20th, not last
    assert result[0].get("today") is not True


def test_already_today_unchanged():
    items = [_item("a", today=True, due=TODAY_STR)]
    result = auto_promote_today(items, today=TODAY)
    count = sum(1 for i in result if i.get("today") is True)
    assert count == 1  # still 1, not 2


def test_finished_not_promoted():
    items = [_item("a", status="finished", due=TODAY_STR)]
    result = auto_promote_today(items, today=TODAY)
    assert result[0].get("today") is not True


def test_max_today_already_at_limit():
    items = [
        _item("a", today=True),
        _item("b", today=True),
        _item("c", today=True),
        _item("d", due=TODAY_STR),
    ]
    result = auto_promote_today(items, today=TODAY)
    assert result[3].get("today") is not True


def test_partial_cap_at_max():
    """2 today=True + 2 eligible → only 1 promoted (cap at 3)."""
    items = [
        _item("a", today=True),
        _item("b", today=True),
        _item("c", due=TODAY_STR),
        _item("d", due=TODAY_STR),
    ]
    result = auto_promote_today(items, today=TODAY)
    promoted = sum(1 for i in result if i.get("today") is True)
    assert promoted == 3


def test_no_eligible_items_unchanged():
    items = [_item("a", due="2026-02-21"), _item("b", recurs="weekly_fri")]
    thursday = date(2026, 2, 19)
    result = auto_promote_today(items, today=thursday)
    assert all(i.get("today") is not True for i in result)


def test_original_items_not_mutated():
    items = [_item("a", due=TODAY_STR)]
    _ = auto_promote_today(items, today=TODAY)
    assert items[0].get("today") is not True


# --- state file tests ---

def test_save_and_load_state(tmp_path):
    p = str(tmp_path / "state.txt")
    save_auto_today_date(p, TODAY)
    assert load_auto_today_date(p) == TODAY_STR


def test_load_state_missing_file(tmp_path):
    assert load_auto_today_date(str(tmp_path / "missing.txt")) is None


def test_load_state_different_date(tmp_path):
    p = str(tmp_path / "state.txt")
    save_auto_today_date(p, date(2026, 2, 19))
    assert load_auto_today_date(p) != TODAY_STR
