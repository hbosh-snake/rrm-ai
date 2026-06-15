import pytest
import copy

from patch import PatchOp, validate, apply
from yaml_utils import read_items


# --- Validation tests ---

def test_set_status_valid(sample_yaml_file):
    items = read_items(str(sample_yaml_file))
    ops = [PatchOp(op="set_status", id="emsn230", value="waiting")]
    errors = validate(ops, items)
    assert errors == []


def test_set_status_unknown_id(sample_yaml_file):
    items = read_items(str(sample_yaml_file))
    ops = [PatchOp(op="set_status", id="nonexistent", value="waiting")]
    errors = validate(ops, items)
    assert len(errors) == 1
    assert "nonexistent" in errors[0]


def test_set_status_invalid_value(sample_yaml_file):
    items = read_items(str(sample_yaml_file))
    ops = [PatchOp(op="set_status", id="emsn230", value="paused")]
    errors = validate(ops, items)
    assert len(errors) == 1
    assert "paused" in errors[0]


def test_set_today_valid(sample_yaml_file):
    items = read_items(str(sample_yaml_file))
    ops = [PatchOp(op="set_today", id="emsn230", value=True)]
    errors = validate(ops, items)
    assert errors == []


def test_set_today_must_be_bool(sample_yaml_file):
    items = read_items(str(sample_yaml_file))
    ops = [PatchOp(op="set_today", id="emsn230", value="true")]
    errors = validate(ops, items)
    assert len(errors) == 1
    assert "bool" in errors[0].lower()


def test_set_today_max_three(sample_yaml_file):
    items = read_items(str(sample_yaml_file))
    # annual_report already has today=True (1 item)
    # Setting two more to True should be fine (3 total)
    ops = [
        PatchOp(op="set_today", id="emsn230", value=True),
        PatchOp(op="set_today", id="budget_review", value=True),
    ]
    errors = validate(ops, items)
    assert errors == []


def test_set_today_exceeds_three(tmp_path):
    from textwrap import dedent
    yaml_content = dedent("""\
        - id: a
          item: "A"
          status: in_progress
          today: true
          next_action: "Do A."
        - id: b
          item: "B"
          status: in_progress
          today: true
          next_action: "Do B."
        - id: c
          item: "C"
          status: in_progress
          today: true
          next_action: "Do C."
        - id: d
          item: "D"
          status: in_progress
          today: false
          next_action: "Do D."
    """)
    p = tmp_path / "test.yaml"
    p.write_text(yaml_content)
    items = read_items(str(p))
    ops = [PatchOp(op="set_today", id="d", value=True)]
    errors = validate(ops, items)
    assert len(errors) == 1
    assert "3" in errors[0]


def test_set_next_action_valid(sample_yaml_file):
    items = read_items(str(sample_yaml_file))
    ops = [PatchOp(op="set_next_action", id="emsn230", value="Send the report.")]
    errors = validate(ops, items)
    assert errors == []


def test_set_next_action_unknown_id(sample_yaml_file):
    items = read_items(str(sample_yaml_file))
    ops = [PatchOp(op="set_next_action", id="nope", value="Do something.")]
    errors = validate(ops, items)
    assert len(errors) == 1


def test_set_next_action_requires_non_empty_string(sample_yaml_file):
    items = read_items(str(sample_yaml_file))
    ops = [PatchOp(op="set_next_action", id="annual_report", value="")]
    errors = validate(ops, items)
    assert len(errors) == 1
    assert "non-empty string" in errors[0]


def test_add_item_valid(sample_yaml_file):
    items = read_items(str(sample_yaml_file))
    ops = [PatchOp(
        op="add_item", id="new_task",
        item="Task: New Task", status="in_progress",
        today=False, next_action="Start working.",
    )]
    errors = validate(ops, items)
    assert errors == []


def test_add_item_duplicate_id(sample_yaml_file):
    items = read_items(str(sample_yaml_file))
    ops = [PatchOp(
        op="add_item", id="emsn230",
        item="Task: Duplicate", status="in_progress",
        today=False, next_action="Clash.",
    )]
    errors = validate(ops, items)
    assert len(errors) == 1
    assert "emsn230" in errors[0]


def test_add_item_invalid_status(sample_yaml_file):
    items = read_items(str(sample_yaml_file))
    ops = [PatchOp(
        op="add_item", id="new_task",
        item="Task: New", status="unknown",
        today=False, next_action="Start.",
    )]
    errors = validate(ops, items)
    assert len(errors) == 1


def test_add_item_today_bool(sample_yaml_file):
    items = read_items(str(sample_yaml_file))
    ops = [PatchOp(
        op="add_item", id="new_task",
        item="Task: New", status="in_progress",
        today="false", next_action="Start.",
    )]
    errors = validate(ops, items)
    assert len(errors) == 1
    assert "bool" in errors[0].lower()


def test_add_item_requires_item_and_next_action(sample_yaml_file):
    items = read_items(str(sample_yaml_file))
    ops = [PatchOp(
        op="add_item", id="new_task",
        status="in_progress", today=False,
    )]
    errors = validate(ops, items)
    assert any("item" in e for e in errors)
    assert any("next_action" in e for e in errors)


def test_unknown_operation_rejected(sample_yaml_file):
    items = read_items(str(sample_yaml_file))
    ops = [PatchOp(op="delete_item", id="annual_report")]
    errors = validate(ops, items)
    assert errors == ["unknown operation 'delete_item'"]


def test_multiple_errors_returned(sample_yaml_file):
    items = read_items(str(sample_yaml_file))
    ops = [
        PatchOp(op="set_status", id="nonexistent", value="waiting"),
        PatchOp(op="set_status", id="emsn230", value="invalid"),
    ]
    errors = validate(ops, items)
    assert len(errors) == 2


# --- Apply tests ---

def test_apply_set_status(sample_yaml_file):
    items = read_items(str(sample_yaml_file))
    ops = [PatchOp(op="set_status", id="emsn230", value="waiting")]
    result = apply(ops, items)
    item = next(i for i in result if i["id"] == "emsn230")
    assert item["status"] == "waiting"


def test_apply_set_today(sample_yaml_file):
    items = read_items(str(sample_yaml_file))
    ops = [PatchOp(op="set_today", id="emsn230", value=True)]
    result = apply(ops, items)
    item = next(i for i in result if i["id"] == "emsn230")
    assert item["today"] is True


def test_apply_set_next_action(sample_yaml_file):
    items = read_items(str(sample_yaml_file))
    ops = [PatchOp(op="set_next_action", id="annual_report", value="Ship it.")]
    result = apply(ops, items)
    item = next(i for i in result if i["id"] == "annual_report")
    assert item["next_action"] == "Ship it."


def test_apply_add_item(sample_yaml_file):
    items = read_items(str(sample_yaml_file))
    ops = [PatchOp(
        op="add_item", id="new_task",
        item="Task: New Task", status="in_progress",
        today=False, next_action="Begin.",
    )]
    result = apply(ops, items)
    assert len(result) == 4
    new = result[-1]
    assert new["id"] == "new_task"
    assert new["item"] == "Task: New Task"
    assert new["status"] == "in_progress"
    assert new["today"] is False
    assert new["next_action"] == "Begin."


def test_apply_preserves_order(sample_yaml_file):
    items = read_items(str(sample_yaml_file))
    ops = [PatchOp(op="set_status", id="emsn230", value="waiting")]
    result = apply(ops, items)
    assert [i["id"] for i in result] == ["annual_report", "emsn230", "budget_review"]


def test_apply_does_not_mutate_original(sample_yaml_file):
    items = read_items(str(sample_yaml_file))
    original_status = items[1]["status"]
    ops = [PatchOp(op="set_status", id="emsn230", value="waiting")]
    apply(ops, items)
    assert items[1]["status"] == original_status


def test_apply_multiple_ops(sample_yaml_file):
    items = read_items(str(sample_yaml_file))
    ops = [
        PatchOp(op="set_status", id="emsn230", value="waiting"),
        PatchOp(op="set_next_action", id="emsn230", value="Wait for Przemek."),
        PatchOp(op="set_today", id="annual_report", value=False),
    ]
    result = apply(ops, items)
    emsn = next(i for i in result if i["id"] == "emsn230")
    assert emsn["status"] == "waiting"
    assert emsn["next_action"] == "Wait for Przemek."
    annual = next(i for i in result if i["id"] == "annual_report")
    assert "today" not in annual
