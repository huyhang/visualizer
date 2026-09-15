"""Private, local writing feedback behind an injectable advisor boundary."""

from __future__ import annotations

import re
from collections import Counter
from threading import BoundedSemaphore
from typing import Protocol

from .errors import ReviewUnavailable
from .richtext import block_text

# US spelling paired with its UK counterpart. Curated rather than derived: a
# "-our" -> "-or" rule would flag "four" and "hour", and an "-ise" -> "-ize"
# rule would flag "rise". Only divergences a novel actually meets are listed.
DIALECT_PAIRS = (
    ("color", "colour"), ("honor", "honour"), ("armor", "armour"),
    ("harbor", "harbour"), ("neighbor", "neighbour"), ("favor", "favour"),
    ("rumor", "rumour"), ("odor", "odour"), ("splendor", "splendour"),
    ("valor", "valour"), ("ardor", "ardour"), ("clamor", "clamour"),
    ("parlor", "parlour"), ("savior", "saviour"), ("behavior", "behaviour"),
    ("labor", "labour"), ("vapor", "vapour"), ("rigor", "rigour"),
    ("center", "centre"), ("theater", "theatre"), ("saber", "sabre"),
    ("scepter", "sceptre"), ("specter", "spectre"), ("luster", "lustre"),
    ("caliber", "calibre"), ("fiber", "fibre"), ("somber", "sombre"),
    ("realize", "realise"), ("recognize", "recognise"),
    ("apologize", "apologise"), ("organize", "organise"),
    ("memorize", "memorise"), ("agonize", "agonise"),
    ("baptize", "baptise"), ("defense", "defence"), ("offense", "offence"),
    ("pretense", "pretence"), ("traveled", "travelled"),
    ("traveling", "travelling"), ("traveler", "traveller"),
    ("jewelry", "jewellery"),
    ("marvelous", "marvellous"), ("counselor", "counsellor"),
    ("gray", "grey"), ("plow", "plough"), ("mold", "mould"),
    ("smolder", "smoulder"), ("cozy", "cosy"),
)

DIALECT_NAMES = {"en-US": "US", "en-GB": "UK"}


def _forms(word: str) -> list[str]:
    """A base spelling and the inflections that share its divergence."""
    stem = word.removesuffix("e")
    return [word, f"{word}s", f"{stem}ed", f"{stem}ing"]


def _dialect_index() -> dict[str, dict[str, str]]:
    """For each dialect, every *foreign* form mapped to its local equivalent."""
    index: dict[str, dict[str, str]] = {"en-US": {}, "en-GB": {}}
    for american, british in DIALECT_PAIRS:
        for us_form, uk_form in zip(_forms(american), _forms(british)):
            # Writing US: British forms are the foreign ones, and vice versa.
            index["en-US"][uk_form] = us_form
            index["en-GB"][us_form] = uk_form
    return index


FOREIGN_FORMS = _dialect_index()


def _match_case(found: str, replacement: str) -> str:
    if found.isupper():
        return replacement.upper()
    if found[:1].isupper():
        return replacement.capitalize()
    return replacement


class WritingAdvisor(Protocol):
    private: bool

    def review(self, document: dict, dialect: str = "en-US") -> list[dict]:
        """Return advisory findings without modifying or retaining prose."""


class RuleBasedWritingAdvisor:
    """Deterministic checks that describe mechanics without judging voice."""

    private = True

    _REPEATED_WORD = re.compile(r"\b([A-Za-z][A-Za-z\u2019'-]*)\s+\1\b", re.IGNORECASE)
    _SPACE_BEFORE_PUNCT = re.compile(r"[ \t]+([,.;:!?])")
    _MULTIPLE_SPACES = re.compile(r" {2,}")
    _SENTENCE = re.compile(r"[^.!?]+(?:[.!?]+|$)")
    _PASSIVE = re.compile(
        r"\b(?:am|is|are|was|were|be|been|being)\s+([a-z]+ed)\b", re.IGNORECASE
    )

    _WORD = re.compile(r"[A-Za-z][A-Za-z\u2019'-]*")

    def review(self, document: dict, dialect: str = "en-US") -> list[dict]:
        """Findings for one validated document.

        The caller validates: the route does it to client-supplied prose before
        it gets here, and prose out of the store was validated on the way in.
        Re-validating deep-copied every document a second time, which on a long
        series is the difference between reading the prose once and twice.
        """
        issues: list[dict] = []
        openings: list[tuple[str, str, str]] = []
        for block in document["content"]:
            text = block_text(block)
            if not text:
                continue
            issues.extend(self._mechanics(block["id"], text))
            issues.extend(self._rhythm(block["id"], text))
            issues.extend(self._dialect(block["id"], text, dialect))
            openings.extend(self._openings(block["id"], text))
        issues.extend(self._repeated_openings(openings))
        return issues

    def _dialect(self, block: str, text: str, dialect: str) -> list[dict]:
        """Spellings from the other side of the Atlantic than the one chosen.

        A manuscript wants one dialect throughout; which one is the writer's
        business, so this reports the mismatch and offers the local spelling
        rather than deciding.
        """
        foreign = FOREIGN_FORMS.get(dialect)
        if not foreign:
            return []
        here = DIALECT_NAMES.get(dialect, dialect)
        there = DIALECT_NAMES["en-GB" if dialect == "en-US" else "en-US"]
        issues = []
        seen: set[str] = set()
        for match in self._WORD.finditer(text):
            found = match.group(0)
            local = foreign.get(found.casefold())
            if local is None or found.casefold() in seen:
                continue
            seen.add(found.casefold())
            issues.append(
                _issue(
                    block, "spelling", f"{there} spelling in a {here} manuscript",
                    found, _match_case(found, local),
                    f"“{found}” is the {there} spelling. "
                    f"A {here} manuscript would use “{_match_case(found, local)}”.",
                )
            )
        return issues

    def _mechanics(self, block: str, text: str) -> list[dict]:
        issues = []
        for match in self._REPEATED_WORD.finditer(text):
            issues.append(
                _issue(
                    block, "grammar", "Repeated word", match.group(0),
                    match.group(1), "This word appears twice in a row.",
                )
            )
        for match in self._SPACE_BEFORE_PUNCT.finditer(text):
            issues.append(
                _issue(
                    block, "punctuation", "Space before punctuation",
                    match.group(0), match.group(1),
                    "Remove the space before this punctuation mark.",
                )
            )
        for match in self._MULTIPLE_SPACES.finditer(text):
            issues.append(
                _issue(
                    block, "spacing", "Extra spaces", match.group(0), " ",
                    "Use a single space between words.",
                )
            )
        return issues

    def _rhythm(self, block: str, text: str) -> list[dict]:
        issues = []
        words = text.split()
        if len(words) > 180:
            issues.append(
                _issue(
                    block, "flow", "Dense paragraph", _excerpt(text), None,
                    "This paragraph is long enough to slow scanning. Consider a break.",
                )
            )
        for sentence in self._SENTENCE.findall(text):
            if len(sentence.split()) > 40:
                issues.append(
                    _issue(
                        block, "flow", "Long sentence", _excerpt(sentence), None,
                        "This sentence has more than 40 words. A natural split may improve clarity.",
                    )
                )
        passive = list(self._PASSIVE.finditer(text))
        if len(passive) >= 2:
            issues.append(
                _issue(
                    block, "style", "Repeated passive construction",
                    _excerpt(passive[0].group(0)), None,
                    "Several passive constructions occur here. Check whether the actor should lead.",
                )
            )
        return issues

    def _openings(self, block: str, text: str) -> list[tuple[str, str, str]]:
        found = []
        for sentence in self._SENTENCE.findall(text):
            words = re.findall(r"[A-Za-z][A-Za-z\u2019'-]*", sentence)
            if len(words) >= 2:
                found.append((" ".join(words[:2]).casefold(), block, sentence.strip()))
        return found

    @staticmethod
    def _repeated_openings(openings: list[tuple[str, str, str]]) -> list[dict]:
        counts = Counter(opening for opening, _, _ in openings)
        reported = set()
        issues = []
        for opening, block, sentence in openings:
            if counts[opening] < 3 or opening in reported:
                continue
            reported.add(opening)
            issues.append(
                _issue(
                    block, "flow", "Repeated sentence opening", _excerpt(sentence),
                    None,
                    f"{counts[opening]} sentences begin with “{opening}”. Varying the rhythm may help.",
                )
            )
        return issues


class SeriesWritingReview:
    """Apply an injected advisor across ordered manuscript drafts.

    Two bounds, because the cost of this scales with the manuscript and a long
    series is very long indeed. ``concurrent_reviews`` is the same shape as the
    export renderer's slot limit: reading a whole series into memory is a cost
    the container can carry a couple of times over and not an unbounded number
    of times, so the third caller is turned away rather than queued behind the
    others. ``max_findings`` bounds the answer instead of the work -- prose
    with one consistent habit (a whole manuscript in the other dialect, say)
    produces a finding per paragraph, and nobody reads the ten-thousandth.
    """

    def __init__(
        self,
        store,
        manuscripts,
        advisor: WritingAdvisor,
        *,
        concurrent_reviews: int = 2,
        max_findings: int = 2000,
    ):
        self.store = store
        self.manuscripts = manuscripts
        self.advisor = advisor
        self.max_findings = max_findings
        self._slots = BoundedSemaphore(concurrent_reviews)

    def review(
        self,
        book: str,
        dialect: str = "en-US",
        *,
        include_alternates: bool = False,
        volume: str | None = None,
    ) -> dict:
        if not self._slots.acquire(blocking=False):
            raise ReviewUnavailable(
                "Another review of this size is already running. Try again shortly."
            )
        try:
            return self._review(book, dialect, include_alternates, volume)
        finally:
            self._slots.release()

    def _review(
        self, book: str, dialect: str, include_alternates: bool, volume: str | None
    ) -> dict:
        volumes = self.manuscripts.prose(book, volume)
        alternates = self._alternates(book, volume) if include_alternates else {}
        findings: list[dict] = []
        counted = 0
        reviewed = 0
        for entry in volumes:
            for section in entry["sections"]:
                rows = alternates.get((entry["id"], section["id"]), [])
                for draft in _candidates(section, rows, include_alternates):
                    reviewed += 1
                    found = self._findings(entry, section, draft, dialect)
                    counted += len(found)
                    if len(findings) < self.max_findings:
                        findings.extend(found[: self.max_findings - len(findings)])
        return {
            "book": book,
            "volume": volume,
            "dialect": dialect,
            "include_alternates": include_alternates,
            "reviewed_drafts": reviewed,
            "private": bool(getattr(self.advisor, "private", False)),
            "issue_count": counted,
            "truncated": counted > len(findings),
            "issues": findings,
        }

    def _alternates(
        self, book: str, volume: str | None
    ) -> dict[tuple[str, str], list[dict]]:
        """Live drafts by section, in one store read, for only what is reviewed."""
        grouped: dict[tuple[str, str], list[dict]] = {}
        for row in self.store.list_book_drafts(book, volume):
            grouped.setdefault((row["volume"], row["section"]), []).append(row)
        return grouped

    def _findings(
        self, volume: dict, section: dict, draft: dict, dialect: str
    ) -> list[dict]:
        """One draft's findings, each carrying where the writer has to go."""
        return [
            {
                **issue,
                **_location(volume, section),
                **draft["identity"],
                "id": (
                    f'{volume["id"]}:{section["id"]}:'
                    f'{draft["identity"]["draft"]}:{issue["id"]}'
                ),
            }
            for issue in self.advisor.review(draft["document"], dialect)
        ]


def _candidates(
    section: dict, rows: list[dict], include_alternates: bool
) -> list[dict]:
    """The primary's prose first, then the named alternates if asked for."""
    primary_id = section["primary_draft_id"]
    row = next((item for item in rows if item["draft"] == primary_id), None)
    drafts = [
        {
            "document": section["document"],
            "identity": {
                "draft": primary_id,
                "draft_name": row["name"] if row else "Primary draft",
                "draft_rev": row["rev"] if row else section["rev"],
                "primary": True,
            },
        }
    ]
    if include_alternates:
        drafts.extend(
            {
                "document": item["document"],
                "identity": {
                    "draft": item["draft"],
                    "draft_name": item["name"],
                    "draft_rev": item["rev"],
                    "primary": False,
                },
            }
            for item in rows
            if item["draft"] != primary_id
        )
    return drafts


def _location(volume: dict, section: dict) -> dict:
    return {
        "volume": volume["id"],
        "volume_title": volume["title"],
        "section": section["id"],
        "section_title": section.get("title"),
        "section_kind": section["kind"],
        "section_number": section.get("number"),
    }


def _excerpt(text: str, limit: int = 100) -> str:
    clean = " ".join(text.split())
    return clean if len(clean) <= limit else clean[: limit - 1].rstrip() + "…"


def _issue(
    block: str,
    category: str,
    title: str,
    excerpt: str,
    replacement: str | None,
    message: str,
) -> dict:
    return {
        "id": f"{block}:{category}:{title}:{excerpt}",
        "block": block,
        "category": category,
        "title": title,
        "message": message,
        "excerpt": excerpt,
        "replacement": replacement,
    }
