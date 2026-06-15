import pytest
from pathlib import Path
from textwrap import dedent


SAMPLE_YAML = dedent("""\
    - id: annual_report
      item: "Document: Annual Report"
      status: in_progress
      today: true
      next_action: "Complete section 3 and send for review."

    - id: emsn230
      item: "Activation: EMSN230 - Sri Lanka"
      status: in_progress
      today: false
      next_action: "Prepare initial maps for the affected area."

    - id: budget_review
      item: "Task: Budget Review"
      status: waiting
      today: false
      next_action: "When finance sends the numbers, compile summary."
""")


@pytest.fixture
def sample_yaml_file(tmp_path):
    p = tmp_path / "rrm-status.yaml"
    p.write_text(SAMPLE_YAML)
    return p
