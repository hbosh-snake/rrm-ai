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
(items with status waiting, one per line as: - **id** — next_action [due: DATE] [recurs: RULE])
(omit due/recurs if not set)

### Notes
(one or two sentences max; omit this section entirely if nothing notable)
(flag only: items marked waiting whose next_action is the user's own work; items due within 7 days that are not in_progress; items that block two or more others and are neither today nor in_progress)
(state facts only, no advice)

Do not add extra sections, counts in headers, separators, or decorative text.
"""
