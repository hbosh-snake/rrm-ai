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
