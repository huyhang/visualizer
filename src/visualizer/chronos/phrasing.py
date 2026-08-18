"""How a finding says a list of ids out loud -- one wording, one place.

Findings are written for a novelist, and every rule that names more than one
thing has to join them the same way: ``'aldric'``, ``'aldric' and 'lyra'``,
``'aldric', 'lyra' and 'bran'``.

The quoting is load-bearing rather than decorative. A client holding the Akasha
grant swaps ``'aldric'`` for ``'Sir Aldric'`` by exact match *including the
quotes* (see ``findings.js``), so a rule that dropped them, or joined with a
comma where another used "and", would quietly break that substitution for its
own messages only.

A leaf module on purpose: the pure rules that need it (``plotline_health``,
``goal_rules``) sit on opposite sides of an import that would otherwise close a
circle, and neither should have to reach through the other to agree on a comma.
"""


def quoted_names(ids) -> str:
    """``'a'``, ``'a' and 'b'``, ``'a', 'b' and 'c'`` -- empty for nothing."""
    quoted = [f"'{i}'" for i in ids]
    if len(quoted) <= 1:
        return "".join(quoted)
    return f"{', '.join(quoted[:-1])} and {quoted[-1]}"


def is_are(items) -> str:
    """Agreement for a subject this module just joined: one thing *is*, several
    *are*. Beside ``quoted_names`` because it is always used with it."""
    return "is" if len(items) == 1 else "are"
