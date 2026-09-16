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


import json
from pathlib import Path

from memory import history_path
from yaml_utils import read_items


def _propose(session, ops, request="change it"):
    session.adapter.results = [(ops, [], "tool_1")]
    return session.submit(request)


def test_accept_writes_the_file(session, sample_yaml_file):
    session.start()
    proposal = _propose(session, [PatchOp(op="set_status", id="emsn230", value="waiting")])

    session.accept(proposal)

    items = read_items(str(sample_yaml_file))
    assert next(i for i in items if i["id"] == "emsn230")["status"] == "waiting"


def test_accept_refreshes_items_and_returns_them(session):
    session.start()
    proposal = _propose(session, [PatchOp(op="set_status", id="emsn230", value="waiting")])

    returned = session.accept(proposal)

    assert next(i for i in returned if i["id"] == "emsn230")["status"] == "waiting"
    assert session.items == returned


def test_accept_creates_a_backup(session, sample_yaml_file):
    session.start()
    proposal = _propose(session, [PatchOp(op="set_status", id="emsn230", value="waiting")])

    session.accept(proposal)

    assert Path(str(sample_yaml_file) + ".bak").exists()


def test_accept_records_a_tool_use_and_its_result(session):
    session.start()
    proposal = _propose(session, [PatchOp(op="set_status", id="emsn230", value="waiting")], "put it on waiting")

    session.accept(proposal)

    user, call, result = session.thread
    assert user == {"role": "user", "content": "put it on waiting"}
    assert call == {"role": "assistant", "content": [{
        "type": "tool_use", "id": "tool_1", "name": "apply_patch",
        "input": {"operations": [{"op": "set_status", "id": "emsn230", "value": "waiting"}]},
    }]}
    assert result["role"] == "user"
    assert result["content"][0]["type"] == "tool_result"
    assert result["content"][0]["tool_use_id"] == "tool_1"
    assert "Applied" in result["content"][0]["content"]


def test_accept_appends_to_history_file(session, sample_yaml_file):
    session.start()
    proposal = _propose(session, [PatchOp(op="set_status", id="emsn230", value="waiting")], "put it on waiting")

    session.accept(proposal)

    data = json.loads(Path(history_path(str(sample_yaml_file))).read_text())
    assert data[-1]["request"] == "put it on waiting"
    assert "emsn230" in data[-1]["result"]


def test_decline_leaves_the_file_byte_identical(session, sample_yaml_file):
    session.start()
    before = sample_yaml_file.read_text()
    proposal = _propose(session, [PatchOp(op="set_status", id="emsn230", value="waiting")])

    session.decline(proposal)

    assert sample_yaml_file.read_text() == before


def test_decline_records_the_rejection_explicitly(session):
    session.start()
    proposal = _propose(session, [PatchOp(op="set_status", id="emsn230", value="waiting")], "put it on waiting")

    session.decline(proposal)

    call, result = session.thread[1], session.thread[2]
    assert call["content"][0]["type"] == "tool_use"
    assert result["content"][0]["tool_use_id"] == call["content"][0]["id"]
    assert "NOT applied" in result["content"][0]["content"]


def test_decline_writes_no_history(session, sample_yaml_file):
    session.start()
    proposal = _propose(session, [PatchOp(op="set_status", id="emsn230", value="waiting")])

    session.decline(proposal)

    assert not Path(history_path(str(sample_yaml_file))).exists()


def test_thread_orders_roles_after_mixed_turns(session):
    session.start()
    session.adapter.results = [("a text answer", [], None)]
    session.submit("a question")
    proposal = _propose(session, [PatchOp(op="set_status", id="emsn230", value="waiting")])
    session.accept(proposal)

    roles = [m["role"] for m in session.thread]
    assert roles == ["user", "assistant", "user", "assistant", "user"]


def test_thread_trims_to_the_cap_oldest_pair_first(session):
    session.start()
    for n in range(12):
        session.adapter.results = [(f"answer {n}", [], None)]
        session.submit(f"question {n}")

    assert len(session.thread) == 20
    assert session.thread[0] == {"role": "user", "content": "question 2"}


def test_trimming_never_orphans_a_tool_result(session):
    session.start()
    for n in range(8):
        proposal = _propose(session, [PatchOp(op="set_status", id="emsn230", value="waiting")], f"change {n}")
        session.decline(proposal)

    assert len(session.thread) <= 20
    assert session.thread[0] == {"role": "user", "content": "change 2"}
    ids_used = {m["content"][0]["id"] for m in session.thread if m["role"] == "assistant"}
    ids_answered = {
        m["content"][0]["tool_use_id"] for m in session.thread
        if m["role"] == "user" and isinstance(m["content"], list)
    }
    assert ids_used == ids_answered


def test_retry_turns_stay_out_of_the_thread(session):
    session.start()
    bad = [PatchOp(op="set_status", id="nonexistent", value="waiting")]
    good = [PatchOp(op="set_status", id="emsn230", value="waiting")]
    session.adapter.results = [(bad, [], "tool_1"), (good, [], "tool_2")]

    proposal = session.submit("put Sri Lanka on waiting")
    session.accept(proposal)

    assert len(session.thread) == 3
    assert session.thread[1]["content"][0]["id"] == "tool_2"
    assert "tool_1" not in str(session.thread)
    assert "Validation failed" not in str(session.thread)


from transcript import transcript_path


def _read_transcript(yaml_file):
    lines = Path(transcript_path(str(yaml_file))).read_text().splitlines()
    return [json.loads(l) for l in lines]


def test_start_prunes_old_transcripts(session, sample_yaml_file, tmp_path):
    from datetime import date, timedelta

    from transcript import KEEP_DAYS, log_turn

    old_day = date.today() - timedelta(days=KEEP_DAYS + 3)
    log_turn(str(sample_yaml_file), {"kind": "submit"}, day=old_day)
    for i in range(KEEP_DAYS):
        log_turn(str(sample_yaml_file), {"kind": "submit"}, day=date.today() - timedelta(days=i))

    session.start()

    assert not Path(transcript_path(str(sample_yaml_file), old_day)).exists()


def test_submit_logs_a_text_reply(session, sample_yaml_file):
    session.start()
    session.adapter.results = [("Annual Report is in focus.", [], None)]

    session.submit("what is in focus?")

    entries = _read_transcript(sample_yaml_file)
    assert len(entries) == 1
    assert entries[0]["kind"] == "submit"
    assert entries[0]["result_kind"] == "text"
    assert entries[0]["response_text"] == "Annual Report is in focus."
    assert entries[0]["retried"] is False
    assert "what is in focus?" in entries[0]["messages"][-1]["content"]


def test_submit_logs_a_patch_proposal(session, sample_yaml_file):
    session.start()
    ops = [PatchOp(op="set_status", id="emsn230", value="waiting")]
    session.adapter.results = [(ops, [], None)]

    session.submit("put Sri Lanka on waiting")

    entries = _read_transcript(sample_yaml_file)
    assert entries[0]["result_kind"] == "patch_proposal"
    assert entries[0]["ops"] == [{
        "op": "set_status", "id": "emsn230", "value": "waiting",
        "item": None, "status": None, "today": None,
        "next_action": None, "due": None, "recurs": None,
    }]


def test_submit_logs_a_validation_failure(session, sample_yaml_file):
    session.start()
    bad = [PatchOp(op="set_status", id="nonexistent", value="waiting")]
    session.adapter.results = [(bad, [], None)]

    session.submit("change something")

    entries = _read_transcript(sample_yaml_file)
    assert entries[0]["result_kind"] == "validation_failure"
    assert any("nonexistent" in e for e in entries[0]["errors"])


def test_submit_logs_retried_flag(session, sample_yaml_file):
    session.start()
    bad = [PatchOp(op="set_status", id="nonexistent", value="waiting")]
    good = [PatchOp(op="set_status", id="emsn230", value="waiting")]
    session.adapter.results = [(bad, [], "tool_1"), (good, [], "tool_2")]

    session.submit("put Sri Lanka on waiting")

    entries = _read_transcript(sample_yaml_file)
    assert entries[0]["retried"] is True
    assert any("nonexistent" in e for e in entries[0]["retry_errors"])


def test_accept_logs_an_outcome_entry(session, sample_yaml_file):
    session.start()
    proposal = _propose(session, [PatchOp(op="set_status", id="emsn230", value="waiting")], "put it on waiting")

    session.accept(proposal)

    entries = _read_transcript(sample_yaml_file)
    assert entries[-1]["kind"] == "accept"
    assert entries[-1]["request"] == "put it on waiting"
    assert entries[-1]["ops"][0]["id"] == "emsn230"


def test_decline_logs_an_outcome_entry(session, sample_yaml_file):
    session.start()
    proposal = _propose(session, [PatchOp(op="set_status", id="emsn230", value="waiting")], "put it on waiting")

    session.decline(proposal)

    entries = _read_transcript(sample_yaml_file)
    assert entries[-1]["kind"] == "decline"
    assert entries[-1]["request"] == "put it on waiting"
