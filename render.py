from rich.console import Console
from rich.markup import escape

from theme import THEME, STATUS_STYLES

STATUS_ORDER = {"in_progress": 0, "waiting": 1}


def _sort_key(item):
    today_rank = 0 if item.get("today") else 1
    status_rank = STATUS_ORDER.get(item.get("status"), 2)
    return (today_rank, status_rank)


def print_status(items: list, console: Console | None = None) -> None:
    """Print items sorted today-first, then by status."""
    if console is None:
        console = Console()

    for item in sorted(items, key=_sort_key):
        status = item["status"]
        style = STATUS_STYLES.get(status, "")
        today_marker = f" [{THEME['today_marker']}]*[/]" if item.get("today") else ""
        id_part = f"[{THEME['item_id']}]{escape(item['id'])}[/]"
        status_tag = f"[{style}]{escape(f'[{status}]')}[/]"
        console.print(
            f"  {status_tag}{today_marker}  {id_part}  {escape(item['item'])}",
            highlight=False
        )

        next_part = f"[{THEME['next_action']}]{escape(item['next_action'])}[/]"
        line2 = f"      next: {next_part}"

        hints = []
        if item.get("due"):
            hints.append(
                f"[{THEME['optional_field']}]due: {escape(str(item['due']))}[/]"
            )
        if item.get("recurs"):
            hints.append(
                f"[{THEME['optional_field']}]recurs: {escape(str(item['recurs']))}[/]"
            )
        if hints:
            line2 += "  " + "  ".join(hints)

        console.print(line2, highlight=False)
