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
