"""How serious a finding is -- the two words, defined once.

``conflict`` is a contradiction in the story; ``info`` is a draft state. That
one distinction decides whether a book's card reads ``conflicted``, which half
of the book report a finding is filed under, and whether the editor marks a row
red or grey. Every layer reads it -- the pure rules (``plotline_health``,
``goal_rules``), the aggregators (``reports``, ``book_health``) and the
presenters -- so it lives on its own here rather than in whichever module
happened to need it first, which is also what keeps those modules from having to
import each other to agree on a word.
"""

CONFLICT = "conflict"
INFO = "info"
