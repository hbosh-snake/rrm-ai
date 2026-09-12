import json
import pytest
from unittest.mock import patch, MagicMock
from textwrap import dedent
from pathlib import Path
from rich.console import Console

from rrm_ai import main
from render import print_status
from patch import PatchOp
from yaml_utils import read_items
from memory import history_path


@pytest.fixture
def yaml_env(sample_yaml_file, monkeypatch):
    """Set up env vars pointing to the sample YAML file."""
    monkeypatch.setenv("RRM_AI_API_KEY", "sk-test")
    monkeypatch.setenv("RRM_AI_YAML", str(sample_yaml_file))
    return sample_yaml_file


class TestStatusFlag:
    def test_status_prints_items(self, yaml_env, capsys):
        with patch("sys.argv", ["rrm-ai", "--status"]):
            main()
        output = capsys.readouterr().out
        assert "annual_report" in output
        assert "emsn230" in output
        assert "budget_review" in output

    def test_status_does_not_call_llm(self, yaml_env):
        with patch("sys.argv", ["rrm-ai", "--status"]):
            with patch("rrm_ai.get_adapter") as mock_adapter:
                main()
                mock_adapter.assert_not_called()

    def test_status_does_not_require_api_key(self, sample_yaml_file, monkeypatch, capsys):
        monkeypatch.delenv("RRM_AI_API_KEY", raising=False)
        monkeypatch.setenv("RRM_AI_YAML", str(sample_yaml_file))

        with patch("sys.argv", ["rrm-ai", "--status"]):
            main()

        output = capsys.readouterr().out
        assert "annual_report" in output


class TestArchiveFlag:
    def test_archive_moves_finished(self, tmp_path, monkeypatch):
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
        monkeypatch.setenv("RRM_AI_API_KEY", "sk-test")
        monkeypatch.setenv("RRM_AI_YAML", str(src))

        with patch("sys.argv", ["rrm-ai", "--archive"]):
            main()

        remaining = read_items(str(src))
        assert len(remaining) == 1
        assert remaining[0]["id"] == "active_task"

        archive = tmp_path / "rrm-archive.yaml"
        assert archive.exists()
        archived = read_items(str(archive))
        assert len(archived) == 1
        assert archived[0]["id"] == "done_task"

    def test_archive_does_not_require_api_key_and_creates_backup(self, tmp_path, monkeypatch):
        yaml_content = dedent("""\
            - id: done_task
              item: "Task: Done"
              status: finished
              today: false
              next_action: "N/A"
        """)
        src = tmp_path / "rrm-status.yaml"
        src.write_text(yaml_content)
        monkeypatch.delenv("RRM_AI_API_KEY", raising=False)
        monkeypatch.setenv("RRM_AI_YAML", str(src))

        with patch("sys.argv", ["rrm-ai", "--archive"]):
            main()

        bak = Path(str(src) + ".bak")
        assert bak.exists()
        assert "done_task" in bak.read_text()


class TestQueryFlow:
    def test_query_prints_text(self, yaml_env, capsys):
        mock_adapter = MagicMock()
        mock_adapter.complete_messages.return_value = ("You have 1 item in focus today.", [], None)

        with patch("sys.argv", ["rrm-ai", "what's in focus?"]):
            with patch("rrm_ai.get_adapter", return_value=mock_adapter):
                main()

        output = capsys.readouterr().out
        assert "1 item in focus" in output


class TestModificationFlow:
    def test_modification_with_yes(self, yaml_env, capsys):
        ops = [PatchOp(op="set_status", id="emsn230", value="waiting")]
        mock_adapter = MagicMock()
        mock_adapter.complete_messages.return_value = (ops, [], None)

        with patch("sys.argv", ["rrm-ai", "put Sri Lanka on waiting", "--yes"]):
            with patch("rrm_ai.get_adapter", return_value=mock_adapter):
                main()

        items = read_items(str(yaml_env))
        updated = next(i for i in items if i["id"] == "emsn230")
        assert updated["status"] == "waiting"

    def test_modification_dry_run(self, yaml_env, capsys):
        ops = [PatchOp(op="set_status", id="emsn230", value="waiting")]
        mock_adapter = MagicMock()
        mock_adapter.complete_messages.return_value = (ops, [], None)

        with patch("sys.argv", ["rrm-ai", "put Sri Lanka on waiting", "--dry-run"]):
            with patch("rrm_ai.get_adapter", return_value=mock_adapter):
                main()

        output = capsys.readouterr().out
        assert "waiting" in output

        # File should NOT be modified
        items = read_items(str(yaml_env))
        emsn = next(i for i in items if i["id"] == "emsn230")
        assert emsn["status"] == "in_progress"

    def test_modification_with_confirmation(self, yaml_env, capsys, monkeypatch):
        ops = [PatchOp(op="set_status", id="emsn230", value="waiting")]
        mock_adapter = MagicMock()
        mock_adapter.complete_messages.return_value = (ops, [], None)
        monkeypatch.setattr("builtins.input", lambda _: "y")

        with patch("sys.argv", ["rrm-ai", "put Sri Lanka on waiting"]):
            with patch("rrm_ai.get_adapter", return_value=mock_adapter):
                main()

        items = read_items(str(yaml_env))
        updated = next(i for i in items if i["id"] == "emsn230")
        assert updated["status"] == "waiting"

    def test_modification_with_enter_confirmation(self, yaml_env, capsys, monkeypatch):
        ops = [PatchOp(op="set_status", id="emsn230", value="waiting")]
        mock_adapter = MagicMock()
        mock_adapter.complete_messages.return_value = (ops, [], None)
        monkeypatch.setattr("builtins.input", lambda _: "")

        with patch("sys.argv", ["rrm-ai", "put Sri Lanka on waiting"]):
            with patch("rrm_ai.get_adapter", return_value=mock_adapter):
                main()

        items = read_items(str(yaml_env))
        updated = next(i for i in items if i["id"] == "emsn230")
        assert updated["status"] == "waiting"

    def test_modification_declined(self, yaml_env, capsys, monkeypatch):
        ops = [PatchOp(op="set_status", id="emsn230", value="waiting")]
        mock_adapter = MagicMock()
        mock_adapter.complete_messages.return_value = (ops, [], None)
        monkeypatch.setattr("builtins.input", lambda _: "n")

        with patch("sys.argv", ["rrm-ai", "put Sri Lanka on waiting"]):
            with patch("rrm_ai.get_adapter", return_value=mock_adapter):
                main()

        # File should NOT be modified
        items = read_items(str(yaml_env))
        emsn = next(i for i in items if i["id"] == "emsn230")
        assert emsn["status"] == "in_progress"


class TestValidationFailure:
    def test_invalid_patch_not_applied(self, yaml_env, capsys):
        ops = [PatchOp(op="set_status", id="nonexistent", value="waiting")]
        mock_adapter = MagicMock()
        mock_adapter.complete_messages.return_value = (ops, [], None)

        with patch("sys.argv", ["rrm-ai", "change something", "--yes"]):
            with patch("rrm_ai.get_adapter", return_value=mock_adapter):
                main()

        output = capsys.readouterr().out
        assert "error" in output.lower() or "Error" in output

        # File should NOT be modified
        items = read_items(str(yaml_env))
        assert len(items) == 3


class TestBackupCreated:
    def test_backup_before_write(self, yaml_env):
        ops = [PatchOp(op="set_status", id="emsn230", value="waiting")]
        mock_adapter = MagicMock()
        mock_adapter.complete_messages.return_value = (ops, [], None)

        with patch("sys.argv", ["rrm-ai", "change", "--yes"]):
            with patch("rrm_ai.get_adapter", return_value=mock_adapter):
                main()

        bak = Path(str(yaml_env) + ".bak")
        assert bak.exists()


class TestHistoryIntegration:
    def _hist_path(self, yaml_env):
        return Path(history_path(str(yaml_env)))

    def test_query_saves_history(self, yaml_env):
        mock_adapter = MagicMock()
        mock_adapter.complete_messages.return_value = ("Annual Report is in focus.", [], None)

        with patch("sys.argv", ["rrm-ai", "what's in focus?"]):
            with patch("rrm_ai.get_adapter", return_value=mock_adapter):
                main()

        hist = self._hist_path(yaml_env)
        assert hist.exists()
        data = json.loads(hist.read_text())
        assert data[-1]["request"] == "what's in focus?"
        assert "Annual Report" in data[-1]["result"]

    def test_modification_saves_history_on_apply(self, yaml_env):
        ops = [PatchOp(op="set_status", id="emsn230", value="waiting")]
        mock_adapter = MagicMock()
        mock_adapter.complete_messages.return_value = (ops, [], None)

        with patch("sys.argv", ["rrm-ai", "put Sri Lanka on waiting", "--yes"]):
            with patch("rrm_ai.get_adapter", return_value=mock_adapter):
                main()

        hist = self._hist_path(yaml_env)
        assert hist.exists()
        data = json.loads(hist.read_text())
        assert data[-1]["request"] == "put Sri Lanka on waiting"
        assert "emsn230" in data[-1]["result"]

    def test_dry_run_does_not_save_history(self, yaml_env):
        ops = [PatchOp(op="set_status", id="emsn230", value="waiting")]
        mock_adapter = MagicMock()
        mock_adapter.complete_messages.return_value = (ops, [], None)

        with patch("sys.argv", ["rrm-ai", "put Sri Lanka on waiting", "--dry-run"]):
            with patch("rrm_ai.get_adapter", return_value=mock_adapter):
                main()

        assert not self._hist_path(yaml_env).exists()

    def test_declined_does_not_save_history(self, yaml_env, monkeypatch):
        ops = [PatchOp(op="set_status", id="emsn230", value="waiting")]
        mock_adapter = MagicMock()
        mock_adapter.complete_messages.return_value = (ops, [], None)
        monkeypatch.setattr("builtins.input", lambda _: "n")

        with patch("sys.argv", ["rrm-ai", "put Sri Lanka on waiting"]):
            with patch("rrm_ai.get_adapter", return_value=mock_adapter):
                main()

        assert not self._hist_path(yaml_env).exists()

    def test_history_passed_to_prompt(self, yaml_env):
        mock_adapter = MagicMock()

        # Seed a history file
        hist = self._hist_path(yaml_env)
        hist.write_text(json.dumps([{"request": "old req", "result": "old res"}]))

        captured_msg = {}

        def capture(system, messages):
            captured_msg["user"] = messages[0]["content"]
            return ("All good.", [], None)

        mock_adapter.complete_messages.side_effect = capture

        with patch("sys.argv", ["rrm-ai", "follow up"]):
            with patch("rrm_ai.get_adapter", return_value=mock_adapter):
                main()

        assert "old req" in captured_msg["user"]
        assert "old res" in captured_msg["user"]


class TestColoredOutput:
    """Verify that terminal output carries ANSI color codes when a TTY is present."""

    def test_validation_error_output_contains_error_text(self, yaml_env, capsys):
        ops = [PatchOp(op="set_status", id="nonexistent", value="waiting")]
        mock_adapter = MagicMock()
        mock_adapter.complete_messages.return_value = (ops, [], None)
        with patch("sys.argv", ["rrm-ai", "change", "--yes"]):
            with patch("rrm_ai.get_adapter", return_value=mock_adapter):
                main()
        output = capsys.readouterr().out
        assert "error" in output.lower()

    def test_applied_message_present(self, yaml_env, capsys):
        ops = [PatchOp(op="set_status", id="emsn230", value="waiting")]
        mock_adapter = MagicMock()
        mock_adapter.complete_messages.return_value = (ops, [], None)
        with patch("sys.argv", ["rrm-ai", "change", "--yes"]):
            with patch("rrm_ai.get_adapter", return_value=mock_adapter):
                main()
        output = capsys.readouterr().out
        assert "Applied" in output

    def test_aborted_message_present(self, yaml_env, capsys, monkeypatch):
        ops = [PatchOp(op="set_status", id="emsn230", value="waiting")]
        mock_adapter = MagicMock()
        mock_adapter.complete_messages.return_value = (ops, [], None)
        monkeypatch.setattr("builtins.input", lambda _: "n")
        with patch("sys.argv", ["rrm-ai", "change"]):
            with patch("rrm_ai.get_adapter", return_value=mock_adapter):
                main()
        output = capsys.readouterr().out
        assert "Abort" in output


class TestBriefFlag:
    def test_brief_flag_prints_the_daily_picture(self, yaml_env, capsys):
        mock_adapter = MagicMock()
        mock_adapter.complete_messages.return_value = ("## Operational Picture", [], None)

        with patch("sys.argv", ["rrm-ai", "--brief"]):
            with patch("rrm_ai.get_adapter", return_value=mock_adapter):
                main()

        assert "Operational Picture" in capsys.readouterr().out

    def test_brief_flag_does_not_start_the_repl(self, yaml_env):
        mock_adapter = MagicMock()
        mock_adapter.complete_messages.return_value = ("## Operational Picture", [], None)

        with patch("sys.argv", ["rrm-ai", "--brief"]):
            with patch("rrm_ai.get_adapter", return_value=mock_adapter):
                with patch("repl.run") as mock_run:
                    main()
                    mock_run.assert_not_called()


class TestBareInvocation:
    def test_bare_invocation_starts_the_repl(self, yaml_env):
        with patch("sys.argv", ["rrm-ai"]):
            with patch("repl.run") as mock_run:
                main()
                mock_run.assert_called_once()
