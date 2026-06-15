"""Tests for optional fields: today (gaps), due, recurs, cross-field invariants, YAML round-trip."""
import copy
import pytest
from textwrap import dedent

from patch import PatchOp, validate, apply
from yaml_utils import read_items, write_items, diff_items


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def base_items():
    """Three items; annual_report has today=true."""
    return [
        {"id": "annual_report", "item": "Document: Annual Report",
         "status": "in_progress", "today": True,
         "next_action": "Complete section 3 and send for review."},
        {"id": "emsn230", "item": "Activation: EMSN230 - Sri Lanka",
         "status": "in_progress", "today": False,
         "next_action": "Prepare initial maps for the affected area."},
        {"id": "budget_review", "item": "Task: Budget Review",
         "status": "waiting", "today": False,
         "next_action": "When finance sends the numbers, compile summary."},
    ]


@pytest.fixture
def three_today_items():
    """Three items all with today=true (max already reached)."""
    return [
        {"id": "a", "item": "A", "status": "in_progress", "today": True,
         "next_action": "Do A."},
        {"id": "b", "item": "B", "status": "in_progress", "today": True,
         "next_action": "Do B."},
        {"id": "c", "item": "C", "status": "in_progress", "today": True,
         "next_action": "Do C."},
        {"id": "d", "item": "D", "status": "in_progress", "today": False,
         "next_action": "Do D."},
    ]


# ---------------------------------------------------------------------------
# Step 1: today field – gap tests (set_today on nonexistent id already covered
# in test_patch.py; add_item + today limit tests are new)
# ---------------------------------------------------------------------------

def test_set_today_nonexistent_id(base_items):
    ops = [PatchOp(op="set_today", id="no_such_id", value=True)]
    errors = validate(ops, base_items)
    assert len(errors) == 1
    assert "no_such_id" in errors[0]


def test_set_today_string_true_rejected(base_items):
    ops = [PatchOp(op="set_today", id="emsn230", value="true")]
    errors = validate(ops, base_items)
    assert len(errors) == 1
    assert "bool" in errors[0].lower()


def test_add_item_today_true_under_limit(base_items):
    """Only 1 item has today=true → adding another is fine."""
    ops = [PatchOp(op="add_item", id="new_task",
                   item="Task: New", status="in_progress",
                   today=True, next_action="Start.")]
    errors = validate(ops, base_items)
    assert errors == []


def test_add_item_today_true_at_limit(three_today_items):
    """3 items already have today=true → add_item with today=true must be rejected."""
    ops = [PatchOp(op="add_item", id="new_task",
                   item="Task: New", status="in_progress",
                   today=True, next_action="Start.")]
    errors = validate(ops, three_today_items)
    assert any("today" in e.lower() or "3" in e for e in errors)


def test_set_today_false_removes_flag(base_items):
    """apply: set_today false should remove the field entirely."""
    ops = [PatchOp(op="set_today", id="annual_report", value=False)]
    result = apply(ops, base_items)
    item = next(i for i in result if i["id"] == "annual_report")
    assert "today" not in item


# ---------------------------------------------------------------------------
# Step 2: due field
# ---------------------------------------------------------------------------

def test_set_due_valid_date(base_items):
    ops = [PatchOp(op="set_due", id="emsn230", value="2026-03-15")]
    errors = validate(ops, base_items)
    assert errors == []


def test_set_due_null_removes_field(base_items):
    items = copy.deepcopy(base_items)
    items[1]["due"] = "2026-01-01"
    ops = [PatchOp(op="set_due", id="emsn230", value=None)]
    errors = validate(ops, items)
    assert errors == []


def test_set_due_invalid_format(base_items):
    ops = [PatchOp(op="set_due", id="emsn230", value="15-03-2026")]
    errors = validate(ops, base_items)
    assert len(errors) == 1
    assert "due" in errors[0].lower() or "format" in errors[0].lower() or "date" in errors[0].lower()


def test_set_due_invalid_calendar_date(base_items):
    ops = [PatchOp(op="set_due", id="emsn230", value="2026-02-30")]
    errors = validate(ops, base_items)
    assert len(errors) == 1


def test_set_due_non_string(base_items):
    ops = [PatchOp(op="set_due", id="emsn230", value=20260315)]
    errors = validate(ops, base_items)
    assert len(errors) == 1


def test_set_due_nonexistent_id(base_items):
    ops = [PatchOp(op="set_due", id="no_such", value="2026-03-15")]
    errors = validate(ops, base_items)
    assert len(errors) == 1
    assert "no_such" in errors[0]


def test_apply_set_due(base_items):
    ops = [PatchOp(op="set_due", id="emsn230", value="2026-03-15")]
    result = apply(ops, base_items)
    item = next(i for i in result if i["id"] == "emsn230")
    assert item["due"] == "2026-03-15"


def test_apply_set_due_null_removes_field(base_items):
    items = copy.deepcopy(base_items)
    items[1]["due"] = "2026-01-01"
    ops = [PatchOp(op="set_due", id="emsn230", value=None)]
    result = apply(ops, items)
    item = next(i for i in result if i["id"] == "emsn230")
    assert "due" not in item


def test_add_item_with_valid_due(base_items):
    ops = [PatchOp(op="add_item", id="new_task",
                   item="Task: New", status="in_progress",
                   today=False, next_action="Start.",
                   due="2026-05-01")]
    errors = validate(ops, base_items)
    assert errors == []


def test_add_item_with_invalid_due(base_items):
    ops = [PatchOp(op="add_item", id="new_task",
                   item="Task: New", status="in_progress",
                   today=False, next_action="Start.",
                   due="not-a-date")]
    errors = validate(ops, base_items)
    assert len(errors) >= 1


# ---------------------------------------------------------------------------
# Step 3: recurs field
# ---------------------------------------------------------------------------

def test_set_recurs_weekly_fri(base_items):
    ops = [PatchOp(op="set_recurs", id="emsn230", value="weekly_fri")]
    errors = validate(ops, base_items)
    assert errors == []


def test_set_recurs_monthly_1(base_items):
    ops = [PatchOp(op="set_recurs", id="emsn230", value="monthly_1")]
    errors = validate(ops, base_items)
    assert errors == []


def test_set_recurs_monthly_last(base_items):
    ops = [PatchOp(op="set_recurs", id="emsn230", value="monthly_last")]
    errors = validate(ops, base_items)
    assert errors == []


def test_set_recurs_null_removes_field(base_items):
    ops = [PatchOp(op="set_recurs", id="emsn230", value=None)]
    errors = validate(ops, base_items)
    assert errors == []


def test_set_recurs_invalid_value(base_items):
    ops = [PatchOp(op="set_recurs", id="emsn230", value="daily")]
    errors = validate(ops, base_items)
    assert len(errors) == 1
    assert "daily" in errors[0] or "recurs" in errors[0].lower()


def test_set_recurs_nonexistent_id(base_items):
    ops = [PatchOp(op="set_recurs", id="no_such", value="weekly_fri")]
    errors = validate(ops, base_items)
    assert len(errors) == 1
    assert "no_such" in errors[0]


def test_apply_set_recurs(base_items):
    ops = [PatchOp(op="set_recurs", id="emsn230", value="weekly_fri")]
    result = apply(ops, base_items)
    item = next(i for i in result if i["id"] == "emsn230")
    assert item["recurs"] == "weekly_fri"


def test_apply_set_recurs_null_removes_field(base_items):
    items = copy.deepcopy(base_items)
    items[1]["recurs"] = "weekly_fri"
    ops = [PatchOp(op="set_recurs", id="emsn230", value=None)]
    result = apply(ops, items)
    item = next(i for i in result if i["id"] == "emsn230")
    assert "recurs" not in item


def test_add_item_with_valid_recurs(base_items):
    ops = [PatchOp(op="add_item", id="new_task",
                   item="Task: New", status="in_progress",
                   today=False, next_action="Start.",
                   recurs="weekly_fri")]
    errors = validate(ops, base_items)
    assert errors == []


def test_add_item_with_invalid_recurs(base_items):
    ops = [PatchOp(op="add_item", id="new_task",
                   item="Task: New", status="in_progress",
                   today=False, next_action="Start.",
                   recurs="hourly")]
    errors = validate(ops, base_items)
    assert len(errors) >= 1


# ---------------------------------------------------------------------------
# Step 4: cross-field invariant  (recurs + finished incompatible)
# ---------------------------------------------------------------------------

def test_set_status_finished_rejected_when_recurs_set(base_items):
    """Item has recurs → setting finished must be rejected."""
    items = copy.deepcopy(base_items)
    items[1]["recurs"] = "weekly_fri"
    ops = [PatchOp(op="set_status", id="emsn230", value="finished")]
    errors = validate(ops, items)
    assert len(errors) >= 1
    assert any("recurs" in e.lower() or "finished" in e.lower() for e in errors)


def test_set_recurs_rejected_when_status_finished(base_items):
    """Item is finished → setting recurs must be rejected."""
    items = copy.deepcopy(base_items)
    items[1]["status"] = "finished"
    ops = [PatchOp(op="set_recurs", id="emsn230", value="weekly_fri")]
    errors = validate(ops, items)
    assert len(errors) >= 1


def test_add_item_recurs_and_finished_rejected(base_items):
    ops = [PatchOp(op="add_item", id="new_task",
                   item="Task: New", status="finished",
                   today=False, next_action="Done.",
                   recurs="weekly_fri")]
    errors = validate(ops, base_items)
    assert len(errors) >= 1


def test_set_recurs_null_then_set_status_finished_accepted(base_items):
    """In same patch: remove recurs first, then set finished → should be accepted."""
    items = copy.deepcopy(base_items)
    items[1]["recurs"] = "weekly_fri"
    ops = [
        PatchOp(op="set_recurs", id="emsn230", value=None),
        PatchOp(op="set_status", id="emsn230", value="finished"),
    ]
    errors = validate(ops, items)
    assert errors == []


# ---------------------------------------------------------------------------
# Step 5: YAML round-trip and diff
# ---------------------------------------------------------------------------

def test_yaml_roundtrip_due(tmp_path):
    p = tmp_path / "rrm-status.yaml"
    items = [{"id": "x", "item": "X", "status": "in_progress",
              "today": False, "due": "2026-03-15",
              "next_action": "Do it."}]
    write_items(str(p), items)
    reloaded = read_items(str(p))
    assert reloaded[0]["due"] == "2026-03-15"


def test_yaml_roundtrip_today_is_bool(tmp_path):
    p = tmp_path / "rrm-status.yaml"
    items = [{"id": "x", "item": "X", "status": "in_progress",
              "today": True, "next_action": "Do it."}]
    write_items(str(p), items)
    reloaded = read_items(str(p))
    assert reloaded[0]["today"] is True


def test_yaml_roundtrip_recurs(tmp_path):
    p = tmp_path / "rrm-status.yaml"
    items = [{"id": "x", "item": "X", "status": "in_progress",
              "today": False, "recurs": "monthly_1",
              "next_action": "Do it."}]
    write_items(str(p), items)
    reloaded = read_items(str(p))
    assert reloaded[0]["recurs"] == "monthly_1"


def test_yaml_no_empty_optional_fields(tmp_path):
    """Items without optional fields must not emit null/empty keys."""
    p = tmp_path / "rrm-status.yaml"
    items = [{"id": "x", "item": "X", "status": "in_progress",
              "today": False, "next_action": "Do it."}]
    write_items(str(p), items)
    text = p.read_text()
    assert "due:" not in text
    assert "recurs:" not in text


def test_yaml_field_order_includes_due_recurs(tmp_path):
    """Field order after write: id, item, status, today, due, recurs, next_action."""
    p = tmp_path / "rrm-status.yaml"
    items = [{"id": "x", "item": "X", "status": "in_progress",
              "today": False, "due": "2026-03-15",
              "recurs": "weekly_fri", "next_action": "Do it."}]
    write_items(str(p), items)
    text = p.read_text()

    def find_pos(key):
        for i, line in enumerate(text.splitlines()):
            s = line.strip().lstrip("- ")
            if s.startswith(key + ":"):
                return i
        return -1

    assert find_pos("id") < find_pos("item") < find_pos("status")
    assert find_pos("status") < find_pos("today") < find_pos("due")
    assert find_pos("due") < find_pos("recurs") < find_pos("next_action")


def test_yaml_remove_optional_field_absent_on_disk(tmp_path):
    """After applying set_due null, the 'due' key must not appear in written YAML."""
    p = tmp_path / "rrm-status.yaml"
    items = [{"id": "x", "item": "X", "status": "in_progress",
              "today": False, "due": "2026-01-01",
              "next_action": "Do it."}]
    write_items(str(p), items)

    reloaded = read_items(str(p))
    ops = [PatchOp(op="set_due", id="x", value=None)]
    patched = apply(ops, reloaded)
    write_items(str(p), patched)

    text = p.read_text()
    assert "due:" not in text


def test_diff_items_detects_due_change(base_items):
    new_items = copy.deepcopy(base_items)
    new_items[1]["due"] = "2026-03-15"
    diffs = diff_items(base_items, new_items)
    assert any("emsn230" in d and "due" in d for d in diffs)


def test_diff_items_detects_recurs_change(base_items):
    new_items = copy.deepcopy(base_items)
    new_items[1]["recurs"] = "weekly_fri"
    diffs = diff_items(base_items, new_items)
    assert any("emsn230" in d and "recurs" in d for d in diffs)
