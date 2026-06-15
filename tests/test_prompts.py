from prompts import build_system_prompt, build_user_message
from yaml_utils import read_items


def test_system_prompt_contains_key_elements():
    prompt = build_system_prompt()
    assert "QUERY" in prompt
    assert "MODIFICATION" in prompt
    assert "apply_patch" in prompt
    assert "today: true" in prompt or "today" in prompt
    assert "finished" in prompt
    assert "next_action" in prompt


def test_system_prompt_mentions_modes():
    prompt = build_system_prompt()
    assert "QUERY" in prompt
    assert "MODIFICATION" in prompt


def test_user_message_includes_input(sample_yaml_file):
    items = read_items(str(sample_yaml_file))
    msg = build_user_message("what's in focus today?", items)
    assert "what's in focus today?" in msg


def test_user_message_includes_items(sample_yaml_file):
    items = read_items(str(sample_yaml_file))
    msg = build_user_message("status?", items)
    assert "annual_report" in msg
    assert "emsn230" in msg
    assert "budget_review" in msg


def test_user_message_includes_status_fields(sample_yaml_file):
    items = read_items(str(sample_yaml_file))
    msg = build_user_message("status?", items)
    assert "in_progress" in msg
    assert "waiting" in msg


class TestHistory:
    def test_no_history_section_when_none(self, sample_yaml_file):
        items = read_items(str(sample_yaml_file))
        msg = build_user_message("status?", items)
        assert "Recent history" not in msg

    def test_no_history_section_when_empty(self, sample_yaml_file):
        items = read_items(str(sample_yaml_file))
        msg = build_user_message("status?", items, history=[])
        assert "Recent history" not in msg

    def test_history_section_present(self, sample_yaml_file):
        items = read_items(str(sample_yaml_file))
        history = [{"request": "put Sri Lanka on waiting", "result": "set_status(emsn230, waiting)"}]
        msg = build_user_message("what changed?", items, history=history)
        assert "Recent history" in msg
        assert "put Sri Lanka on waiting" in msg
        assert "set_status(emsn230, waiting)" in msg

    def test_history_entries_are_numbered(self, sample_yaml_file):
        items = read_items(str(sample_yaml_file))
        history = [
            {"request": "req1", "result": "res1"},
            {"request": "req2", "result": "res2"},
        ]
        msg = build_user_message("follow up", items, history=history)
        assert "[1]" in msg
        assert "[2]" in msg

    def test_history_appears_before_yaml(self, sample_yaml_file):
        items = read_items(str(sample_yaml_file))
        history = [{"request": "old req", "result": "old res"}]
        msg = build_user_message("follow up", items, history=history)
        assert msg.index("Recent history") < msg.index("Current RRM status")
