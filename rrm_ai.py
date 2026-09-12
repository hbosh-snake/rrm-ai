import argparse
import sys
from pathlib import Path

from rich.console import Console
from rich.markdown import Markdown
from rich.theme import Theme

from config import load_config, load_yaml_path
from yaml_utils import read_items, write_items, backup, diff_items, archive_finished
from patch import PatchOp, validate, apply
from adapters import get_adapter
from prompts import build_system_prompt, build_user_message
from daily_brief import build_daily_brief_prompt
from memory import history_path, load_history, save_history, format_patch_result
from theme import THEME, LLM_MARKDOWN_THEME
from auto_today import auto_promote_today, load_auto_today_date, save_auto_today_date
from render import print_status


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="rrm-ai",
        description="Natural language CLI for RRM status management",
    )
    parser.add_argument("text", nargs="?", help="Natural language input")
    parser.add_argument(
        "--dry-run", action="store_true", help="Show patch but do not save"
    )
    parser.add_argument("--yes", action="store_true", help="Apply without confirmation")
    parser.add_argument(
        "--status", action="store_true", help="Print current state (no LLM)"
    )
    parser.add_argument(
        "--archive", action="store_true", help="Move finished items to archive"
    )

    args = parser.parse_args()
    if args.status or args.archive:
        yaml_path = load_yaml_path()
        config = None
    else:
        config = load_config()
        yaml_path = config.yaml_path
    auto_today_state = str(Path(yaml_path).with_name("rrm-auto-today.txt"))
    console = Console()

    from datetime import date as _date
    today = _date.today()
    already_promoted_today = load_auto_today_date(auto_today_state) == today.strftime("%Y-%m-%d")

    def maybe_promote(items: list) -> list:
        if already_promoted_today:
            return items
        promoted = auto_promote_today(items, today=today)
        if diff_items(items, promoted):
            backup(yaml_path)
            write_items(yaml_path, promoted)
        save_auto_today_date(auto_today_state, today)
        return promoted

    if args.status:
        items = read_items(yaml_path)
        items = maybe_promote(items)
        print_status(items, console=console)
        return

    if args.archive:
        archive_path = str(Path(yaml_path).with_name("rrm-archive.yaml"))
        backup(yaml_path)
        archive_file = Path(archive_path)
        if archive_file.exists():
            backup(archive_path)
        archive_finished(yaml_path, archive_path)
        console.print(f"[{THEME['success']}]Finished items archived.[/]")
        return

    daily_brief = not args.text
    if daily_brief:
        args.text = build_daily_brief_prompt()

    items = read_items(yaml_path)
    items = maybe_promote(items)
    adapter = get_adapter(config)
    hist_path = history_path(yaml_path)
    history = load_history(hist_path)

    system = build_system_prompt()
    user_msg = build_user_message(args.text, items, None if daily_brief else history)
    messages = [{"role": "user", "content": user_msg}]
    result, assistant_content, tool_use_id = adapter.complete_messages(system, messages)

    if isinstance(result, str):
        # Query response — text only
        tts_text = result  # extension point for TTS
        console.push_theme(Theme(LLM_MARKDOWN_THEME))
        console.print(Markdown(tts_text))
        console.pop_theme()
        save_history(hist_path, history, args.text, tts_text)
        return

    # Modification response — list of PatchOps
    ops: list[PatchOp] = result
    errors = validate(ops, items)
    if errors and tool_use_id is not None:
        # Feed the validation errors back as a tool_result and let the LLM retry.
        error_text = "Validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
        retry_messages = messages + [
            {"role": "assistant", "content": assistant_content},
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": error_text,
                        "is_error": True,
                    }
                ],
            },
        ]
        result, _, _ = adapter.complete_messages(system, retry_messages)
        if isinstance(result, str):
            # LLM explained why it can't comply — show the message.
            console.push_theme(Theme(LLM_MARKDOWN_THEME))
            console.print(Markdown(result))
            console.pop_theme()
            save_history(hist_path, history, args.text, result)
            return
        ops = result
        errors = validate(ops, items)

    if errors:
        console.print(f"[{THEME['error_header']}]Validation errors:[/]")
        for e in errors:
            console.print(f"  [{THEME['error_line']}]\u2717 {e}[/]")
        return

    new_items = apply(ops, items)
    diffs = diff_items(items, new_items)

    console.print(f"[{THEME['diff_header']}]Proposed changes:[/]")
    for d in diffs:
        style = THEME["diff_add"] if d.strip().startswith("+") else THEME["diff_change"]
        console.print(f"  [{style}]\u2022{d}[/]")

    if args.dry_run:
        return

    if not args.yes:
        answer = input("\nApply? [Y/n] ").strip().lower()
        if answer not in ("", "y"):
            console.print(f"[{THEME['aborted']}]Aborted.[/]")
            return

    backup(yaml_path)
    write_items(yaml_path, new_items)
    save_history(hist_path, history, args.text, format_patch_result(ops))
    console.print(f"[{THEME['success']}]Applied.[/]")


if __name__ == "__main__":
    main()
