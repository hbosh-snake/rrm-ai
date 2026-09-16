import pytest
from pathlib import Path
from textwrap import dedent

from yaml_utils import read_items, write_items, backup, diff_items, archive_finished


def test_read_items(sample_yaml_file):
    items = read_items(str(sample_yaml_file))
    assert len(items) == 3
    assert items[0]["id"] == "annual_report"
    assert items[1]["id"] == "emsn230"
    assert items[2]["id"] == "budget_review"


def test_read_items_fields(sample_yaml_file):
    items = read_items(str(sample_yaml_file))
    item = items[0]
    assert item["item"] == "Document: Annual Report"
    assert item["status"] == "in_progress"
    assert item["today"] is True
    assert item["next_action"] == "Complete section 3 and send for review."


def test_read_items_rejects_invalid_status_with_ids(tmp_path):
    src = tmp_path / "rrm-status.yaml"
    src.write_text(
        dedent(
            """\
            - id: ok_item
              item: "Task: OK"
              status: waiting
              today: false
              next_action: "Wait"

            - id: bad_one
              item: "Task: Bad One"
              status: in progress
              today: false
              next_action: "Fix me"

            - id: bad_two
              item: "Task: Bad Two"
              status: blocked
              today: false
              next_action: "Fix me too"
            """
        )
    )

    with pytest.raises(ValueError) as excinfo:
        read_items(str(src))

    msg = str(excinfo.value)
    assert "bad_one" in msg
    assert "bad_two" in msg
    assert "in_progress" in msg
    assert "waiting" in msg
    assert "finished" in msg


def test_write_items_preserves_order(sample_yaml_file):
    items = read_items(str(sample_yaml_file))
    write_items(str(sample_yaml_file), items)
    reloaded = read_items(str(sample_yaml_file))
    assert len(reloaded) == 3
    for orig, new in zip(items, reloaded):
        assert dict(orig) == dict(new)


def test_write_items_preserves_field_order(sample_yaml_file):
    items = read_items(str(sample_yaml_file))
    write_items(str(sample_yaml_file), items)
    text = sample_yaml_file.read_text()
    # Strip "- " prefix from list item lines, then filter for field keys
    def normalize(line):
        s = line.strip()
        return s[2:] if s.startswith("- ") else s
    lines = [normalize(l) for l in text.splitlines()
             if normalize(l).startswith(("id:", "item:", "status:", "today:", "next_action:"))]
    # First item fields should appear in order: id, item, status, today, next_action
    first_five = lines[:5]
    assert first_five[0].startswith("id:")
    assert first_five[1].startswith("item:")
    assert first_five[2].startswith("status:")
    assert first_five[3].startswith("today:")
    assert first_five[4].startswith("next_action:")


def test_write_items_inserts_blank_row_between_items(tmp_path):
    p = tmp_path / "rrm-status.yaml"
    items = [
        {
            "id": "a",
            "item": "Task A",
            "status": "in_progress",
            "today": False,
            "next_action": "Do A.",
        },
        {
            "id": "b",
            "item": "Task B",
            "status": "waiting",
            "today": False,
            "next_action": "Do B.",
        },
    ]

    write_items(str(p), items)

    assert p.read_text() == dedent(
        """\
        - id: a
          item: Task A
          status: in_progress
          today: false
          next_action: Do A.

        - id: b
          item: Task B
          status: waiting
          today: false
          next_action: Do B.
        """
    )


def test_write_items_compacts_blank_rows_within_item(tmp_path):
    p = tmp_path / "rrm-status.yaml"
    p.write_text(
        dedent(
            """\
            - id: a
              item: Task A

              status: in_progress
              today: false

              next_action: Do A.

            - id: b
              item: Task B
              status: waiting
              today: false
              next_action: Do B.
            """
        )
    )

    items = read_items(str(p))
    write_items(str(p), items)

    assert p.read_text() == dedent(
        """\
        - id: a
          item: Task A
          status: in_progress
          today: false
          next_action: Do A.

        - id: b
          item: Task B
          status: waiting
          today: false
          next_action: Do B.
        """
    )


def test_backup_creates_file(sample_yaml_file):
    backup(str(sample_yaml_file))
    bak = Path(str(sample_yaml_file) + ".bak")
    assert bak.exists()
    assert bak.read_text() == sample_yaml_file.read_text()


def test_diff_items_detects_status_change(sample_yaml_file):
    items = read_items(str(sample_yaml_file))
    import copy
    new_items = copy.deepcopy(items)
    new_items[1]["status"] = "waiting"
    diffs = diff_items(items, new_items)
    assert len(diffs) == 1
    assert "emsn230" in diffs[0]
    assert "in_progress" in diffs[0]
    assert "waiting" in diffs[0]


def test_diff_items_detects_today_change(sample_yaml_file):
    items = read_items(str(sample_yaml_file))
    import copy
    new_items = copy.deepcopy(items)
    new_items[0]["today"] = False
    diffs = diff_items(items, new_items)
    assert len(diffs) == 1
    assert "annual_report" in diffs[0]


def test_diff_items_detects_next_action_change(sample_yaml_file):
    items = read_items(str(sample_yaml_file))
    import copy
    new_items = copy.deepcopy(items)
    new_items[0]["next_action"] = "Send final version."
    diffs = diff_items(items, new_items)
    assert len(diffs) == 1
    assert "annual_report" in diffs[0]
    assert "next_action" in diffs[0]


def test_diff_items_detects_added_item(sample_yaml_file):
    items = read_items(str(sample_yaml_file))
    import copy
    new_items = copy.deepcopy(items)
    new_items.append({
        "id": "new_item",
        "item": "Task: New Item",
        "status": "in_progress",
        "today": False,
        "next_action": "Do something.",
    })
    diffs = diff_items(items, new_items)
    assert any("new_item" in d for d in diffs)
    assert any("added" in d.lower() for d in diffs)


def test_diff_items_no_changes(sample_yaml_file):
    items = read_items(str(sample_yaml_file))
    diffs = diff_items(items, items)
    assert diffs == []


def test_archive_finished(tmp_path):
    yaml_content = dedent("""\
        - id: done_task
          item: "Task: Done"
          status: finished
          today: false
          next_action: "N/A"

        - id: active_task
          item: "Task: Active"
          status: in_progress
          today: true
          next_action: "Keep working."
    """)
    src = tmp_path / "rrm-status.yaml"
    src.write_text(yaml_content)
    archive = tmp_path / "rrm-archive.yaml"

    archive_finished(str(src), str(archive))

    remaining = read_items(str(src))
    assert len(remaining) == 1
    assert remaining[0]["id"] == "active_task"

    archived = read_items(str(archive))
    assert len(archived) == 1
    assert archived[0]["id"] == "done_task"


def test_archive_appends_to_existing(tmp_path):
    src_content = dedent("""\
        - id: done2
          item: "Task: Done 2"
          status: finished
          today: false
          next_action: "N/A"
    """)
    archive_content = dedent("""\
        - id: done1
          item: "Task: Done 1"
          status: finished
          today: false
          next_action: "N/A"
    """)
    src = tmp_path / "rrm-status.yaml"
    src.write_text(src_content)
    archive = tmp_path / "rrm-archive.yaml"
    archive.write_text(archive_content)

    archive_finished(str(src), str(archive))

    archived = read_items(str(archive))
    assert len(archived) == 2
    assert archived[0]["id"] == "done1"
    assert archived[1]["id"] == "done2"


def test_diff_items_detects_removed_item(sample_yaml_file):
    items = read_items(str(sample_yaml_file))
    diffs = diff_items(items, items[:2])
    assert diffs == ["  - budget_review  removed: Task: Budget Review"]
