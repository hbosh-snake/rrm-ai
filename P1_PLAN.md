# Plan: P1 — Consolidate Patch Tests

## Context

P0 is green (147 tests passing). P1 consolidates `test_patch.py` and `test_optional_fields.py` by removing a confirmed duplicate and collapsing repetitive parametric cases into `@pytest.mark.parametrize`.

---

## Overlap analysis

### Exact duplicate (remove from `test_patch.py`)

| `test_patch.py` | `test_optional_fields.py` | Reason to remove |
|---|---|---|
| `test_set_today_must_be_bool` — `set_today id="emsn230" value="true"` | `test_set_today_string_true_rejected` — same op, id, value, assertion | Identical behaviour, identical assertion |

**Action:** delete `test_set_today_must_be_bool` from `test_patch.py`.

### Repetitive cases within `test_optional_fields.py` (parametrize)

**Group 1 — valid `recurs` values (3 identical-structure tests):**
- `test_set_recurs_weekly_fri`
- `test_set_recurs_monthly_1`
- `test_set_recurs_monthly_last`

Each calls `validate([PatchOp(op="set_recurs", id="emsn230", value=VALUE)], base_items)` and asserts `errors == []`.

**Action:** replace the three tests with one parametrized test:
```python
@pytest.mark.parametrize("value", ["weekly_fri", "monthly_1", "monthly_last"])
def test_set_recurs_valid_values(base_items, value):
    ops = [PatchOp(op="set_recurs", id="emsn230", value=value)]
    errors = validate(ops, base_items)
    assert errors == []
```

**Group 2 — invalid `due` values (3 identical-structure tests):**
- `test_set_due_invalid_format` — `value="15-03-2026"`
- `test_set_due_invalid_calendar_date` — `value="2026-02-30"`
- `test_set_due_non_string` — `value=20260315`

Each calls `validate([PatchOp(op="set_due", id="emsn230", value=VALUE)], base_items)` and asserts `len(errors) == 1`.

**Action:** replace the three tests with one parametrized test:
```python
@pytest.mark.parametrize("value", [
    "15-03-2026",   # wrong format
    "2026-02-30",   # invalid calendar date
    20260315,       # non-string
])
def test_set_due_invalid_values(base_items, value):
    ops = [PatchOp(op="set_due", id="emsn230", value=value)]
    errors = validate(ops, base_items)
    assert len(errors) == 1
```

---

## What stays unchanged

- All other tests in `test_patch.py` — cover core ops (`set_status`, `set_next_action`, `add_item`, `apply_*`, immutability, ordering, multi-op) with no counterpart in `test_optional_fields.py`.
- All remaining tests in `test_optional_fields.py` — cover `set_due` (valid, null, nonexistent-id, apply, add_item), `set_recurs` (null, invalid, nonexistent-id, apply, add_item), cross-field invariant, YAML round-trip, diff detection.

---

## Files changed

| File | Change |
|---|---|
| `tests/test_patch.py` | Delete `test_set_today_must_be_bool` |
| `tests/test_optional_fields.py` | Replace 3 `test_set_recurs_*` valid tests with one parametrized; replace 3 `test_set_due_invalid_*` tests with one parametrized |

---

## Net effect on test count

| Before | After | Delta |
|---|---|---|
| 147 | 146 | −1 (exact duplicate removed from test_patch.py) |

The 4 merged→2 parametrized tests yield the same 6 pytest items (3+3), no net change there.

---

## Verification

```
pytest tests/test_patch.py tests/test_optional_fields.py -v
```

All 146 tests must pass. The removed name (`test_set_today_must_be_bool`) must not appear. The new parametrized names (`test_set_recurs_valid_values[weekly_fri]`, etc.) must appear.
