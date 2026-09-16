import pytest
from unittest.mock import MagicMock, patch

from adapters import AnthropicAdapter, get_adapter
from patch import PatchOp
from config import Config


def _make_config(provider="anthropic"):
    return Config(
        provider=provider,
        model="claude-sonnet-4-5-20250514",
        api_key="sk-test",
        yaml_path="/tmp/test.yaml",
    )


def _mock_text_response(text):
    """Create a mock Anthropic response with text content."""
    content_block = MagicMock()
    content_block.type = "text"
    content_block.text = text

    response = MagicMock()
    response.content = [content_block]
    response.stop_reason = "end_turn"
    return response


def _mock_tool_use_response(tool_input):
    """Create a mock Anthropic response with tool use content."""
    content_block = MagicMock()
    content_block.type = "tool_use"
    content_block.name = "apply_patch"
    content_block.input = tool_input

    response = MagicMock()
    response.content = [content_block]
    response.stop_reason = "tool_use"
    return response


def _mock_mixed_response(text, tool_input):
    """Create a mock Anthropic response with both text and tool use."""
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = text

    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.name = "apply_patch"
    tool_block.input = tool_input

    response = MagicMock()
    response.content = [text_block, tool_block]
    response.stop_reason = "tool_use"
    return response


class TestAnthropicAdapter:
    def test_text_response_returns_string(self):
        adapter = AnthropicAdapter(_make_config())
        mock_response = _mock_text_response("Here is the current status.")
        adapter.client = MagicMock()
        adapter.client.messages.create.return_value = mock_response

        result = adapter.complete("system prompt", "what's the status?")
        assert isinstance(result, str)
        assert result == "Here is the current status."

    def test_tool_use_response_returns_patch_ops(self):
        adapter = AnthropicAdapter(_make_config())
        tool_input = {
            "operations": [
                {"op": "set_status", "id": "emsn230", "value": "waiting"},
                {"op": "set_next_action", "id": "emsn230", "value": "Wait for Przemek."},
            ]
        }
        mock_response = _mock_tool_use_response(tool_input)
        adapter.client = MagicMock()
        adapter.client.messages.create.return_value = mock_response

        result = adapter.complete("system prompt", "put Sri Lanka on waiting")
        assert isinstance(result, list)
        assert len(result) == 2
        assert isinstance(result[0], PatchOp)
        assert result[0].op == "set_status"
        assert result[0].id == "emsn230"
        assert result[0].value == "waiting"

    def test_tool_use_add_item(self):
        adapter = AnthropicAdapter(_make_config())
        tool_input = {
            "operations": [
                {
                    "op": "add_item",
                    "id": "emsn240",
                    "item": "Activation: EMSN240 - Greece",
                    "status": "in_progress",
                    "today": False,
                    "next_action": "Prepare initial assessment.",
                }
            ]
        }
        mock_response = _mock_tool_use_response(tool_input)
        adapter.client = MagicMock()
        adapter.client.messages.create.return_value = mock_response

        result = adapter.complete("system prompt", "add Greece activation")
        assert len(result) == 1
        op = result[0]
        assert op.op == "add_item"
        assert op.id == "emsn240"
        assert op.item == "Activation: EMSN240 - Greece"
        assert op.today is False

    def test_mixed_response_ignores_text_and_returns_tool_result(self):
        adapter = AnthropicAdapter(_make_config())
        mock_response = _mock_mixed_response(
            "Here's what I'll change:",
            {"operations": [{"op": "set_status", "id": "x", "value": "waiting"}]},
        )
        adapter.client = MagicMock()
        adapter.client.messages.create.return_value = mock_response

        result = adapter.complete("system prompt", "do something")
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0].op == "set_status"

    def test_tool_schema_is_passed(self):
        adapter = AnthropicAdapter(_make_config())
        adapter.client = MagicMock()
        adapter.client.messages.create.return_value = _mock_text_response("ok")

        adapter.complete("sys", "msg")

        call_kwargs = adapter.client.messages.create.call_args
        assert "tools" in call_kwargs.kwargs
        tools = call_kwargs.kwargs["tools"]
        assert len(tools) == 1
        assert tools[0]["name"] == "apply_patch"


class TestGetAdapter:
    def test_get_anthropic_adapter(self):
        adapter = get_adapter(_make_config("anthropic"))
        assert isinstance(adapter, AnthropicAdapter)

    def test_get_unknown_adapter_raises(self):
        with pytest.raises(ValueError, match="openai"):
            get_adapter(_make_config("openai"))


def test_add_item_without_today_defaults_to_false():
    from adapters import _parse_tool_input

    ops = _parse_tool_input({"operations": [
        {"op": "add_item", "id": "x", "item": "X", "status": "waiting", "next_action": "Do it."},
        {"op": "set_status", "id": "y", "value": "waiting"},
    ]})

    assert ops[0].today is False
    assert ops[1].today is None
