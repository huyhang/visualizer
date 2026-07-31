"""Interval arithmetic on the abstract integer tick line.

Intervals are half-open ``[start, end)`` (design §4): touching endpoints do not
overlap, which is exactly the boundary both the temporal-conflict and the
ordering rules want. Pure integer math -- no I/O.
"""


def overlaps(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    """Whether half-open intervals ``[a_start, a_end)`` and ``[b_start, b_end)``
    overlap. Touching (``a_end == b_start``) is *not* an overlap."""
    return a_start < b_end and b_start < a_end
