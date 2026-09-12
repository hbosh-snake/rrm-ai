"""Terminal frontend for the interactive session.

Owns input, rendering, and command dispatch. Knows nothing about the
Anthropic API or patch validation - that all lives in session.py.
"""

from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from rich.console import Console
from rich.markdown import Markdown
from rich.theme import Theme

from daily_brief import build_daily_brief_prompt
from render import print_status
from session import PatchProposal, TextReply, ValidationFailure
from theme import LLM_MARKDOWN_THEME, THEME
from yaml_utils import archive_finished, backup

COMMANDS = {
    "/status": "Reprint the current item list",
    "/brief": "Ask for the daily operational picture",
    "/archive": "Move finished items to the archive",
    "/help": "Show this list",
    "/quit": "Exit the session",
}


def parse_input(text: str) -> tuple[str, str]:
    """Classify one line of input.

    Returns (kind, payload) where kind is empty, command, unknown, or llm.
    A leading slash always means a command, so a typo never costs an API call.
    """
    stripped = text.strip()
    if not stripped:
        return ("empty", "")
    if stripped.startswith("/"):
        if stripped in COMMANDS:
            return ("command", stripped)
        return ("unknown", stripped)
    return ("llm", stripped)


PROMPT = "rrm> "


def _print_markdown(text: str, console: Console) -> None:
    console.push_theme(Theme(LLM_MARKDOWN_THEME))
    console.print(Markdown(text))
    console.pop_theme()


def _print_diffs(diffs: list[str], console: Console) -> None:
    console.print(f"[{THEME['diff_header']}]Proposed changes:[/]")
    for d in diffs:
        style = THEME["diff_add"] if d.strip().startswith("+") else THEME["diff_change"]
        console.print(f"  [{style}]•{d}[/]")


def handle_command(name: str, session, console: Console) -> bool:
    """Run one slash command. Returns False when the loop should stop."""
    if name == "/quit":
        return False
    if name == "/status":
        print_status(session.items, console=console)
    elif name == "/help":
        for command, description in COMMANDS.items():
            console.print(f"  [{THEME['item_id']}]{command}[/]  {description}")
    elif name == "/archive":
        archive_path = str(Path(session.yaml_path).with_name("rrm-archive.yaml"))
        backup(session.yaml_path)
        if Path(archive_path).exists():
            backup(archive_path)
        archive_finished(session.yaml_path, archive_path)
        session.start()
        console.print(f"[{THEME['success']}]Finished items archived.[/]")
        print_status(session.items, console=console)
    elif name == "/brief":
        result = session.submit(build_daily_brief_prompt())
        if isinstance(result, TextReply):
            _print_markdown(result.text, console)
    return True


def _handle_proposal(proposal: PatchProposal, session, console: Console) -> None:
    _print_diffs(proposal.diffs, console)
    answer = input("\nApply? [Y/n] ").strip().lower()
    if answer in ("", "y"):
        session.accept(proposal)
        console.print(f"[{THEME['success']}]Applied.[/]")
        print_status(session.items, console=console)
    else:
        session.decline(proposal)
        console.print(f"[{THEME['aborted']}]Declined.[/]")


def run(session, console: Console | None = None) -> None:
    """Drive the session until the user quits."""
    if console is None:
        console = Console()

    session.start()
    print_status(session.items, console=console)
    console.print(f"[{THEME['aborted']}]Type /help for commands.[/]")

    prompt_session = PromptSession()

    while True:
        try:
            raw = prompt_session.prompt(
                PROMPT,
                completer=WordCompleter(
                    list(COMMANDS) + [i["id"] for i in session.items]
                ),
            )
        except KeyboardInterrupt:
            continue
        except EOFError:
            break

        kind, payload = parse_input(raw)

        if kind == "empty":
            continue
        if kind == "unknown":
            console.print(f"[{THEME['error_line']}]unknown command: {payload}[/]")
            continue
        if kind == "command":
            if not handle_command(payload, session, console):
                break
            continue

        try:
            with console.status("thinking..."):
                result = session.submit(payload)
        except KeyboardInterrupt:
            console.print(f"[{THEME['aborted']}]Cancelled.[/]")
            continue
        except Exception as exc:
            console.print(f"[{THEME['error_line']}]{type(exc).__name__}: {exc}[/]")
            continue

        if isinstance(result, TextReply):
            _print_markdown(result.text, console)
        elif isinstance(result, ValidationFailure):
            console.print(f"[{THEME['error_header']}]Validation errors:[/]")
            for e in result.errors:
                console.print(f"  [{THEME['error_line']}]✗ {e}[/]")
        elif isinstance(result, PatchProposal):
            _handle_proposal(result, session, console)
