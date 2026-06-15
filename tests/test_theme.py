from theme import THEME, STATUS_STYLES
from patch import VALID_STATUSES


def test_theme_has_required_keys():
    required = [
        "status_in_progress", "status_waiting", "status_finished",
        "today_marker", "item_id", "next_action", "optional_field",
        "diff_header", "diff_add", "diff_change",
        "error_header", "error_line", "success", "aborted",
    ]
    for key in required:
        assert key in THEME, f"Missing theme key: {key!r}"


def test_status_styles_covers_all_statuses():
    for s in VALID_STATUSES:
        assert s in STATUS_STYLES, f"Status {s!r} not in STATUS_STYLES"
