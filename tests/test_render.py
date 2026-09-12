from rich.console import Console

from render import print_status


def test_print_status_emits_ansi_codes(capsys):
    items = [{"id": "x", "item": "Some task", "status": "in_progress",
              "today": False, "next_action": "do it"}]
    print_status(items, console=Console(force_terminal=True))
    output = capsys.readouterr().out
    assert "\x1b[" in output


def test_print_status_today_marker_present(capsys):
    items = [{"id": "z", "item": "Focus task", "status": "in_progress",
              "today": True, "next_action": "focus"}]
    print_status(items, console=Console())
    output = capsys.readouterr().out
    assert "*" in output


def test_print_status_no_today_marker_when_false(capsys):
    items = [{"id": "z", "item": "Task", "status": "waiting",
              "today": False, "next_action": "wait"}]
    print_status(items, console=Console())
    output = capsys.readouterr().out
    assert "*" not in output


def test_today_items_sort_first(capsys):
    items = [
        {"id": "later", "item": "B", "status": "in_progress",
         "today": False, "next_action": "b"},
        {"id": "focus", "item": "A", "status": "waiting",
         "today": True, "next_action": "a"},
    ]
    print_status(items, console=Console())
    output = capsys.readouterr().out
    assert output.index("focus") < output.index("later")


def test_due_and_recurs_hints_rendered(capsys):
    items = [{"id": "r", "item": "Recurring", "status": "in_progress",
              "today": False, "next_action": "do",
              "due": "2026-09-30", "recurs": "weekly_fri"}]
    print_status(items, console=Console())
    output = capsys.readouterr().out
    assert "due: 2026-09-30" in output
    assert "recurs: weekly_fri" in output
