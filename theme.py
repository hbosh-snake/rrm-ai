"""
Color/style configuration for terminal output.
All output styles are defined here. To change the visual theme,
edit the THEME dict values (Rich style strings).
"""

THEME = {
    # Status indicators
    "status_in_progress": "cyan",
    "status_waiting": "yellow",
    "status_finished": "dim",
    # Item display
    "today_marker": "bold green",
    "item_id": "bold",
    "next_action": "dim",
    "optional_field": "dim cyan",
    # Patch diff
    "diff_header": "bold",
    "diff_add": "green",
    "diff_change": "cyan",
    # Errors
    "error_header": "bold red",
    "error_line": "red",
    # Outcomes
    "success": "bold green",
    "aborted": "dim",
}

# Rich markdown theme for LLM text responses.
# Keys are Rich's internal markdown style names.
LLM_MARKDOWN_THEME = {
    "markdown.h1": "bold green",
    "markdown.h2": "bold cyan",
    "markdown.h3": "cyan",
    "markdown.bullet": "bold green",
    "markdown.item.bullet": "green",
    "markdown.code": "yellow",
    "markdown.code_block": "yellow",
}

STATUS_STYLES = {
    "in_progress": THEME["status_in_progress"],
    "waiting": THEME["status_waiting"],
    "finished": THEME["status_finished"],
}
