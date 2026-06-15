from anthropic import Anthropic

from config import Config
from patch import PatchOp


TOOL_SCHEMA = {
    "name": "apply_patch",
    "description": (
        "Apply a list of patch operations to the RRM status file. "
        "Use this tool ONLY when the user explicitly requests a change. "
        "For queries, respond with text only."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "operations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "op": {
                            "type": "string",
                            "enum": [
                                "set_status",
                                "set_today",
                                "set_next_action",
                                "set_due",
                                "set_recurs",
                                "add_item",
                            ],
                        },
                        "id": {
                            "type": "string",
                            "description": "The item id to operate on",
                        },
                        "value": {
                            "description": (
                                "New value for set_status (in_progress|waiting|finished), "
                                "set_today (true|false), set_next_action (string), "
                                "set_due (YYYY-MM-DD or null), set_recurs (weekly_fri|monthly_1|monthly_last or null)"
                            ),
                        },
                        "item": {
                            "type": "string",
                            "description": "Item description (for add_item only)",
                        },
                        "status": {
                            "type": "string",
                            "enum": ["in_progress", "waiting", "finished"],
                            "description": "Status (for add_item only)",
                        },
                        "today": {
                            "type": "boolean",
                            "description": "Today flag (for add_item only)",
                        },
                        "next_action": {
                            "type": "string",
                            "description": "Next action (for add_item only)",
                        },
                        "due": {
                            "type": ["string", "null"],
                            "pattern": r"^\d{4}-\d{2}-\d{2}$",
                            "description": "Due date in YYYY-MM-DD format (for add_item only), or null",
                        },
                        "recurs": {
                            "type": ["string", "null"],
                            "enum": ["weekly_fri", "monthly_1", "monthly_last", None],
                            "description": "Recurrence pattern (for add_item only), or null",
                        },
                    },
                    "required": ["op", "id"],
                },
            },
        },
        "required": ["operations"],
    },
}


def _parse_tool_input(tool_input: dict) -> list[PatchOp]:
    ops = []
    for raw in tool_input["operations"]:
        ops.append(
            PatchOp(
                op=raw["op"],
                id=raw["id"],
                value=raw.get("value"),
                item=raw.get("item"),
                status=raw.get("status"),
                today=raw.get("today"),
                next_action=raw.get("next_action"),
                due=raw.get("due"),
                recurs=raw.get("recurs"),
            )
        )
    return ops


class AnthropicAdapter:
    def __init__(self, config: Config):
        self.config = config
        self.client = Anthropic(api_key=config.api_key)

    def complete_messages(
        self, system: str, messages: list[dict]
    ) -> tuple[str | list[PatchOp], list, str | None]:
        """Return (result, raw_assistant_content, tool_use_id).

        raw_assistant_content and tool_use_id are needed to construct a
        tool_result follow-up turn when validation fails.
        """
        response = self.client.messages.create(
            model=self.config.model,
            max_tokens=1024,
            system=system,
            messages=messages,
            tools=[TOOL_SCHEMA],
        )

        text_blocks = [b for b in response.content if b.type == "text"]
        tool_blocks = [b for b in response.content if b.type == "tool_use"]

        has_text = any(b.text.strip() for b in text_blocks)
        has_tool = len(tool_blocks) > 0

        if has_text and has_tool:
            # Model added preamble before tool call; ignore the text.
            has_text = False

        if has_tool:
            tool_block = tool_blocks[0]
            return _parse_tool_input(tool_block.input), response.content, tool_block.id

        text = text_blocks[0].text if text_blocks else ""
        return text, response.content, None

    def complete(self, system: str, user: str) -> str | list[PatchOp]:
        result, _, _ = self.complete_messages(
            system, [{"role": "user", "content": user}]
        )
        return result


def get_adapter(config: Config):
    if config.provider == "anthropic":
        return AnthropicAdapter(config)
    raise ValueError(
        f"Unsupported provider: '{config.provider}' (only 'anthropic' is supported)"
    )
