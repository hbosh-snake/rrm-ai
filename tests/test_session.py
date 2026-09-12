from unittest.mock import MagicMock

import pytest

from patch import PatchOp
from session import Session, TextReply, load_items


class FakeAdapter:
    """Adapter stub returning canned results and recording what it was sent."""

    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def complete_messages(self, system, messages):
        self.calls.append({"system": system, "messages": messages})
        return self.results.pop(0)


@pytest.fixture
def session(sample_yaml_file):
    adapter = FakeAdapter([])
    return Session(str(sample_yaml_file), adapter)


def test_load_items_reads_the_file(sample_yaml_file):
    items = load_items(str(sample_yaml_file))
    assert {i["id"] for i in items} == {"annual_report", "emsn230", "budget_review"}


def test_start_populates_items(session):
    items = session.start()
    assert len(items) == 3
    assert session.items == items


def test_start_leaves_thread_empty(session):
    session.start()
    assert session.thread == []


def test_submit_query_returns_text_reply(session):
    session.start()
    session.adapter.results = [("Annual Report is in focus.", [], None)]

    result = session.submit("what is in focus?")

    assert isinstance(result, TextReply)
    assert result.text == "Annual Report is in focus."


def test_submit_query_records_both_turns(session):
    session.start()
    session.adapter.results = [("Annual Report is in focus.", [], None)]

    session.submit("what is in focus?")

    assert session.thread == [
        {"role": "user", "content": "what is in focus?"},
        {"role": "assistant", "content": "Annual Report is in focus."},
    ]


def test_thread_stores_naked_user_text_without_yaml(session):
    session.start()
    session.adapter.results = [("ok", [], None)]

    session.submit("what is in focus?")

    assert "annual_report" not in session.thread[0]["content"]


def test_sent_message_carries_the_yaml_snapshot(session):
    session.start()
    session.adapter.results = [("ok", [], None)]

    session.submit("what is in focus?")

    sent = session.adapter.calls[0]["messages"][-1]["content"]
    assert "annual_report" in sent
    assert "what is in focus?" in sent


def test_second_submit_sends_prior_turns_then_fresh_snapshot(session):
    session.start()
    session.adapter.results = [("first", [], None), ("second", [], None)]

    session.submit("one")
    session.submit("two")

    messages = session.adapter.calls[1]["messages"]
    assert messages[0] == {"role": "user", "content": "one"}
    assert messages[1] == {"role": "assistant", "content": "first"}
    assert "annual_report" in messages[2]["content"]
    assert "two" in messages[2]["content"]


def test_only_the_newest_message_holds_a_snapshot(session):
    session.start()
    session.adapter.results = [("first", [], None), ("second", [], None)]

    session.submit("one")
    session.submit("two")

    messages = session.adapter.calls[1]["messages"]
    snapshot_count = sum(1 for m in messages if "annual_report" in m["content"])
    assert snapshot_count == 1


def test_failed_api_call_leaves_thread_untouched(session):
    session.start()
    adapter = MagicMock()
    adapter.complete_messages.side_effect = RuntimeError("network down")
    session.adapter = adapter

    with pytest.raises(RuntimeError):
        session.submit("what is in focus?")

    assert session.thread == []


from session import PatchProposal, ValidationFailure


def test_submit_valid_patch_returns_proposal(session):
    session.start()
    ops = [PatchOp(op="set_status", id="emsn230", value="waiting")]
    session.adapter.results = [(ops, [], None)]

    result = session.submit("put Sri Lanka on waiting")

    assert isinstance(result, PatchProposal)
    assert result.ops == ops
    assert result.request == "put Sri Lanka on waiting"
    assert any("emsn230" in d for d in result.diffs)


def test_proposal_does_not_touch_the_thread(session):
    session.start()
    ops = [PatchOp(op="set_status", id="emsn230", value="waiting")]
    session.adapter.results = [(ops, [], None)]

    session.submit("put Sri Lanka on waiting")

    assert session.thread == []


def test_proposal_does_not_write_the_file(session, sample_yaml_file):
    session.start()
    before = sample_yaml_file.read_text()
    ops = [PatchOp(op="set_status", id="emsn230", value="waiting")]
    session.adapter.results = [(ops, [], None)]

    session.submit("put Sri Lanka on waiting")

    assert sample_yaml_file.read_text() == before


def test_invalid_patch_is_retried_once(session):
    session.start()
    bad = [PatchOp(op="set_status", id="nonexistent", value="waiting")]
    good = [PatchOp(op="set_status", id="emsn230", value="waiting")]
    session.adapter.results = [(bad, [], "tool_1"), (good, [], "tool_2")]

    result = session.submit("put Sri Lanka on waiting")

    assert isinstance(result, PatchProposal)
    assert result.ops == good
    assert len(session.adapter.calls) == 2


def test_retry_sends_the_errors_as_a_tool_result(session):
    session.start()
    bad = [PatchOp(op="set_status", id="nonexistent", value="waiting")]
    good = [PatchOp(op="set_status", id="emsn230", value="waiting")]
    session.adapter.results = [(bad, [], "tool_1"), (good, [], "tool_2")]

    session.submit("put Sri Lanka on waiting")

    retry_messages = session.adapter.calls[1]["messages"]
    tool_result = retry_messages[-1]["content"][0]
    assert tool_result["type"] == "tool_result"
    assert tool_result["tool_use_id"] == "tool_1"
    assert tool_result["is_error"] is True
    assert "nonexistent" in tool_result["content"]


def test_retry_answering_in_text_returns_a_text_reply(session):
    session.start()
    bad = [PatchOp(op="set_status", id="nonexistent", value="waiting")]
    session.adapter.results = [
        (bad, [], "tool_1"),
        ("There is no item with that id.", [], None),
    ]

    result = session.submit("mark the thing done")

    assert isinstance(result, TextReply)
    assert result.text == "There is no item with that id."
    assert session.thread[-1]["content"] == "There is no item with that id."


def test_still_invalid_after_retry_returns_validation_failure(session):
    session.start()
    bad = [PatchOp(op="set_status", id="nonexistent", value="waiting")]
    session.adapter.results = [(bad, [], "tool_1"), (bad, [], "tool_2")]

    result = session.submit("change something")

    assert isinstance(result, ValidationFailure)
    assert any("nonexistent" in e for e in result.errors)
    assert session.thread == []


def test_invalid_patch_without_tool_use_id_is_not_retried(session):
    session.start()
    bad = [PatchOp(op="set_status", id="nonexistent", value="waiting")]
    session.adapter.results = [(bad, [], None)]

    result = session.submit("change something")

    assert isinstance(result, ValidationFailure)
    assert len(session.adapter.calls) == 1
