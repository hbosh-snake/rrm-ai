import pytest

from repl import COMMANDS, parse_input


def test_blank_input_is_empty():
    assert parse_input("") == ("empty", "")
    assert parse_input("   ") == ("empty", "")


@pytest.mark.parametrize("name", ["/status", "/brief", "/archive", "/help", "/quit"])
def test_known_commands_are_recognised(name):
    assert parse_input(name) == ("command", name)


def test_commands_tolerate_surrounding_whitespace():
    assert parse_input("  /status  ") == ("command", "/status")


def test_unknown_slash_command_is_not_sent_to_the_llm():
    assert parse_input("/nope") == ("unknown", "/nope")


def test_plain_text_goes_to_the_llm():
    assert parse_input("what is in focus?") == ("llm", "what is in focus?")


def test_text_containing_status_is_not_a_command():
    assert parse_input("status of emsn230?") == ("llm", "status of emsn230?")


def test_command_with_trailing_words_is_unknown():
    assert parse_input("/brief me on emsn230") == ("unknown", "/brief me on emsn230")


def test_every_command_has_help_text():
    assert set(COMMANDS) == {"/status", "/brief", "/archive", "/help", "/quit"}
    assert all(COMMANDS.values())


from unittest.mock import MagicMock

from rich.console import Console

from patch import PatchOp
from repl import handle_command
from session import PatchProposal, TextReply, ValidationFailure


def _console():
    return Console(force_terminal=False)


def test_status_command_renders_without_calling_the_llm(capsys):
    session = MagicMock()
    session.items = [{"id": "emsn230", "item": "Activation", "status": "waiting",
                      "today": False, "next_action": "wait"}]

    keep_going = handle_command("/status", session, _console())

    assert keep_going is True
    session.submit.assert_not_called()
    assert "emsn230" in capsys.readouterr().out


def test_help_command_lists_every_command(capsys):
    handle_command("/help", MagicMock(), _console())
    output = capsys.readouterr().out
    for name in ["/status", "/brief", "/archive", "/help", "/quit"]:
        assert name in output


def test_quit_command_stops_the_loop():
    assert handle_command("/quit", MagicMock(), _console()) is False


def test_brief_command_calls_the_llm(capsys):
    session = MagicMock()
    session.submit.return_value = TextReply("## Operational Picture")

    handle_command("/brief", session, _console())

    session.submit.assert_called_once()
    assert "Operational Picture" in capsys.readouterr().out


from pathlib import Path
from textwrap import dedent
from unittest.mock import patch

from yaml_utils import read_items


def test_archive_command_moves_finished_items_and_refreshes_the_session(tmp_path, capsys):
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

    session = MagicMock()
    session.yaml_path = str(src)
    session.items = [{"id": "active_task", "item": "Task: Active", "status": "in_progress",
                      "today": True, "next_action": "Keep working."}]

    keep_going = handle_command("/archive", session, _console())

    assert keep_going is True
    session.start.assert_called_once()

    remaining = read_items(str(src))
    assert len(remaining) == 1
    assert remaining[0]["id"] == "active_task"

    archive = tmp_path / "rrm-archive.yaml"
    assert archive.exists()
    archived = read_items(str(archive))
    assert archived[0]["id"] == "done_task"

    assert Path(str(src) + ".bak").exists()

    output = capsys.readouterr().out
    assert "archived" in output.lower()


def test_run_dispatches_each_result_kind_and_survives_a_ctrl_c(capsys):
    from repl import run

    session = MagicMock()
    session.items = [{"id": "demo001", "item": "Activation: Demo", "status": "in_progress",
                      "today": True, "next_action": "Do the thing."}]

    def submit_side_effect(text):
        if text == "ask something":
            return TextReply("Here is the answer.")
        if text == "an invalid change":
            return ValidationFailure(["id not found"])
        if text == "make a change":
            return PatchProposal(ops=[], diffs=["+ x"], request=text)
        if text == "trigger a crash":
            raise RuntimeError("boom")
        raise AssertionError(f"unexpected submit text: {text}")

    session.submit.side_effect = submit_side_effect

    prompts = [
        "ask something",
        KeyboardInterrupt(),
        "trigger a crash",
        "an invalid change",
        "make a change",
        EOFError(),
    ]

    fake_prompt_session = MagicMock()
    fake_prompt_session.prompt.side_effect = prompts

    with patch("repl.PromptSession", return_value=fake_prompt_session):
        with patch("builtins.input", return_value="y"):
            run(session, console=_console())

    assert session.submit.call_count == 4
    session.accept.assert_called_once()

    output = capsys.readouterr().out
    assert "Here is the answer." in output
    assert "RuntimeError" in output and "boom" in output
    assert "id not found" in output
    assert "Proposed changes" in output
    assert "Applied" in output
