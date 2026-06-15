from datetime import date


def build_daily_brief_prompt() -> str:
    today = date.today().strftime("%A, %Y-%m-%d")
    return f"""\
Today is {today}.

Give me the operational picture. Use this exact structure — no deviations:

## Operational Picture — {today}

### Today
(items with today: true, one per line as: - **id** — next_action)
(if none, write: No items marked as today.)

### In Progress
(items with status in_progress and today != true, one per line as: - **id** — next_action [due: DATE] [recurs: RULE])
(omit due/recurs if not set)

### Waiting
(items with status waiting, one per line as: - **id** — next_action)

### Notes
(one or two sentences max; flag drift or blockers only; omit this section entirely if nothing notable)

Do not add extra sections, counts in headers, separators, or decorative text.
"""
