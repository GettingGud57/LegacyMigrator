"""
Property-based tests for diff.reconcile, using Hypothesis.

Instead of hand-writing a few example tables, Hypothesis generates hundreds of
random little tables. For each one we make a random change we KNOW matters
(edit a cell, drop a row, duplicate a row, add a row, swap two values) and check
that reconcile notices. We also check that reshuffling the rows never matters.

If one of these ever fails, Hypothesis prints the smallest table it could find
that breaks it, which is usually a great clue.

These all pass today: they lock in that the whole-row multiset idea is sound.
They can't catch type drift (finding 2), because they work on Python values,
which is the level where the types are already gone.
"""
import datetime as dt
from decimal import Decimal

from hypothesis import given, settings, strategies as st

import diff

# Column values in the shapes SQL Server hands back: ints, short text, 2-place decimals,
# dates, timestamps, booleans, and NULL (None) for all of them.
VALUES = {
    "qty": st.none() | st.integers(-1000, 1000),
    "name": st.none() | st.text(alphabet="abcAB é", max_size=4),
    "price": st.none() | st.decimals(min_value=-10000, max_value=10000, places=2,
                                     allow_nan=False, allow_infinity=False),
    "day": st.none() | st.dates(dt.date(2013, 1, 1), dt.date(2016, 12, 31)),
    "at": st.none() | st.datetimes(dt.datetime(2013, 1, 1), dt.datetime(9999, 12, 31)),
    "flag": st.none() | st.booleans(),
}
COLUMNS = list(VALUES)


@st.composite
def tables(draw, min_rows=1):
    n = draw(st.integers(min_rows, 12))
    rows = []
    for i in range(n):
        row = {"id": i}  # unique id, so swapping values between rows always changes something
        for col in COLUMNS:
            row[col] = draw(VALUES[col])
        rows.append(row)
    return rows


def copy_rows(rows):
    return [dict(r) for r in rows]


def is_fail(a, b, **kwargs):
    return diff.reconcile(a, b, **kwargs)["status"] == "fail"


@settings(max_examples=300, deadline=None)
@given(tables(min_rows=0), st.randoms(use_true_random=False))
def test_shuffled_copy_passes(rows, rnd):
    other = copy_rows(rows)
    rnd.shuffle(other)
    assert not is_fail(rows, other)


@settings(max_examples=300, deadline=None)
@given(tables(), st.data())
def test_changed_cell_fails(rows, data):
    i = data.draw(st.integers(0, len(rows) - 1))
    col = data.draw(st.sampled_from(COLUMNS))
    new_value = data.draw(VALUES[col].filter(lambda v: not _same(v, rows[i][col])))
    other = copy_rows(rows)
    other[i][col] = new_value
    assert is_fail(rows, other), f"changed {col} on row {i} from {rows[i][col]!r} to {new_value!r}"


@settings(max_examples=200, deadline=None)
@given(tables(), st.data())
def test_dropped_row_fails(rows, data):
    i = data.draw(st.integers(0, len(rows) - 1))
    other = copy_rows(rows)
    del other[i]
    assert is_fail(rows, other)


@settings(max_examples=200, deadline=None)
@given(tables(), st.data())
def test_duplicated_row_fails(rows, data):
    i = data.draw(st.integers(0, len(rows) - 1))
    assert is_fail(rows, copy_rows(rows) + [dict(rows[i])])


@settings(max_examples=200, deadline=None)
@given(tables(min_rows=2), st.data())
def test_swapped_values_fail(rows, data):
    col = data.draw(st.sampled_from(COLUMNS))
    i, j = data.draw(st.lists(st.integers(0, len(rows) - 1), min_size=2, max_size=2, unique=True))
    if _same(rows[i][col], rows[j][col]):
        return  # swapping equal values changes nothing, so nothing to detect
    other = copy_rows(rows)
    other[i][col], other[j][col] = other[j][col], other[i][col]
    assert is_fail(rows, other)


@settings(max_examples=200, deadline=None)
@given(tables(), st.data())
def test_change_in_ignored_column_passes_and_other_columns_still_count(rows, data):
    ignored = data.draw(st.sampled_from(COLUMNS))
    i = data.draw(st.integers(0, len(rows) - 1))
    other = copy_rows(rows)
    other[i][ignored] = data.draw(VALUES[ignored])
    assert not is_fail(rows, other, ignore_cols=[ignored])

    # ...but a change in any other column is still caught
    col = data.draw(st.sampled_from([c for c in COLUMNS if c != ignored]))
    other[i][col] = data.draw(VALUES[col].filter(lambda v: not _same(v, rows[i][col])))
    assert is_fail(rows, other, ignore_cols=[ignored])


def _same(a, b):
    """Equal the way a database would see it: same value and both NULL or both not."""
    if a is None or b is None:
        return a is b
    if isinstance(a, Decimal) or isinstance(b, Decimal):
        return Decimal(a) == Decimal(b)
    return a == b
