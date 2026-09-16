import json
from datetime import date, timedelta
from pathlib import Path

from transcript import KEEP_DAYS, log_turn, prune, transcript_dir, transcript_path


class TestTranscriptPath:
    def test_derives_dir_from_yaml_path(self, tmp_path):
        yaml = str(tmp_path / "rrm-status.yaml")
        assert transcript_dir(yaml) == str(tmp_path / "rrm-transcripts")

    def test_defaults_to_today(self, tmp_path):
        yaml = str(tmp_path / "rrm-status.yaml")
        expected = str(tmp_path / "rrm-transcripts" / f"{date.today().isoformat()}.jsonl")
        assert transcript_path(yaml) == expected

    def test_accepts_explicit_day(self, tmp_path):
        yaml = str(tmp_path / "rrm-status.yaml")
        day = date(2026, 1, 1)
        assert transcript_path(yaml, day) == str(tmp_path / "rrm-transcripts" / "2026-01-01.jsonl")


class TestLogTurn:
    def test_creates_dir_and_file(self, tmp_path):
        yaml = str(tmp_path / "rrm-status.yaml")
        log_turn(yaml, {"kind": "submit"})
        assert Path(transcript_path(yaml)).exists()

    def test_appends_one_json_line_per_call(self, tmp_path):
        yaml = str(tmp_path / "rrm-status.yaml")
        log_turn(yaml, {"kind": "submit", "n": 1})
        log_turn(yaml, {"kind": "submit", "n": 2})

        lines = Path(transcript_path(yaml)).read_text().splitlines()
        assert [json.loads(l)["n"] for l in lines] == [1, 2]


class TestPrune:
    def test_leaves_files_within_the_window(self, tmp_path):
        yaml = str(tmp_path / "rrm-status.yaml")
        today = date.today()
        for i in range(KEEP_DAYS):
            log_turn(yaml, {"n": i}, day=today - timedelta(days=i))

        prune(yaml)

        remaining = sorted(Path(transcript_dir(yaml)).glob("*.jsonl"))
        assert len(remaining) == KEEP_DAYS

    def test_deletes_files_older_than_the_window(self, tmp_path):
        yaml = str(tmp_path / "rrm-status.yaml")
        today = date.today()
        old_day = today - timedelta(days=KEEP_DAYS + 3)
        log_turn(yaml, {"n": 0}, day=old_day)
        for i in range(KEEP_DAYS):
            log_turn(yaml, {"n": i + 1}, day=today - timedelta(days=i))

        prune(yaml)

        remaining = {p.name for p in Path(transcript_dir(yaml)).glob("*.jsonl")}
        assert f"{old_day.isoformat()}.jsonl" not in remaining

    def test_deletes_old_files_even_when_few_exist(self, tmp_path):
        yaml = str(tmp_path / "rrm-status.yaml")
        today = date.today()
        old_day = today - timedelta(days=KEEP_DAYS + 5)
        log_turn(yaml, {"n": 0}, day=old_day)
        log_turn(yaml, {"n": 1}, day=today)

        prune(yaml)

        remaining = {p.name for p in Path(transcript_dir(yaml)).glob("*.jsonl")}
        assert remaining == {f"{today.isoformat()}.jsonl"}

    def test_no_op_when_dir_missing(self, tmp_path):
        yaml = str(tmp_path / "rrm-status.yaml")
        prune(yaml)  # must not raise
