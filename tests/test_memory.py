import json
from pathlib import Path

import pytest

from memory import history_path, load_history, save_history, format_patch_result, MAX_ENTRIES
from patch import PatchOp


class TestHistoryPath:
    def test_derives_from_yaml_path(self, tmp_path):
        yaml = str(tmp_path / "rrm-status.yaml")
        assert history_path(yaml) == str(tmp_path / "rrm-history.json")


class TestLoadHistory:
    def test_returns_empty_when_file_missing(self, tmp_path):
        path = str(tmp_path / "rrm-history.json")
        assert load_history(path) == []

    def test_returns_empty_on_malformed_json(self, tmp_path):
        p = tmp_path / "rrm-history.json"
        p.write_text("not json {{{")
        assert load_history(str(p)) == []

    def test_loads_entries(self, tmp_path):
        p = tmp_path / "rrm-history.json"
        data = [{"request": "what's in focus?", "result": "Annual Report."}]
        p.write_text(json.dumps(data))
        assert load_history(str(p)) == data

    def test_loads_multiple_entries(self, tmp_path):
        p = tmp_path / "rrm-history.json"
        data = [
            {"request": "req1", "result": "res1"},
            {"request": "req2", "result": "res2"},
        ]
        p.write_text(json.dumps(data))
        assert load_history(str(p)) == data


class TestSaveHistory:
    def test_creates_file_with_first_entry(self, tmp_path):
        path = str(tmp_path / "rrm-history.json")
        save_history(path, [], "mark X as done", "set_status(x, finished)")
        saved = json.loads(Path(path).read_text())
        assert saved == [{"request": "mark X as done", "result": "set_status(x, finished)"}]

    def test_appends_to_existing(self, tmp_path):
        path = str(tmp_path / "rrm-history.json")
        existing = [{"request": "old req", "result": "old res"}]
        save_history(path, existing, "new req", "new res")
        saved = json.loads(Path(path).read_text())
        assert len(saved) == 2
        assert saved[-1] == {"request": "new req", "result": "new res"}

    def test_caps_at_max_entries(self, tmp_path):
        path = str(tmp_path / "rrm-history.json")
        existing = [{"request": f"req{i}", "result": f"res{i}"} for i in range(MAX_ENTRIES)]
        save_history(path, existing, "newest req", "newest res")
        saved = json.loads(Path(path).read_text())
        assert len(saved) == MAX_ENTRIES
        assert saved[-1]["request"] == "newest req"
        assert saved[0]["request"] == "req1"

    def test_does_not_mutate_input_list(self, tmp_path):
        path = str(tmp_path / "rrm-history.json")
        original = [{"request": "r", "result": "x"}]
        copy = list(original)
        save_history(path, original, "new", "new")
        assert original == copy


class TestFormatPatchResult:
    def test_set_status(self):
        ops = [PatchOp(op="set_status", id="emsn230", value="waiting")]
        assert format_patch_result(ops) == "set_status(emsn230, waiting)"

    def test_set_today(self):
        ops = [PatchOp(op="set_today", id="annual_report", value=True)]
        assert format_patch_result(ops) == "set_today(annual_report, True)"

    def test_set_next_action(self):
        ops = [PatchOp(op="set_next_action", id="budget_review", value="Send reminder.")]
        assert format_patch_result(ops) == "set_next_action(budget_review)"

    def test_add_item(self):
        ops = [PatchOp(op="add_item", id="emsn240")]
        assert format_patch_result(ops) == "add_item(emsn240)"

    def test_multiple_ops(self):
        ops = [
            PatchOp(op="set_status", id="emsn230", value="waiting"),
            PatchOp(op="set_next_action", id="emsn230", value="Wait for Przemek."),
        ]
        assert format_patch_result(ops) == "set_status(emsn230, waiting), set_next_action(emsn230)"

    def test_empty_ops(self):
        assert format_patch_result([]) == ""
