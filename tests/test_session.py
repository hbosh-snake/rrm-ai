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
