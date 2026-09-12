"""Terminal frontend for the interactive session.

Owns input, rendering, and command dispatch. Knows nothing about the
Anthropic API or patch validation - that all lives in session.py.
"""

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
