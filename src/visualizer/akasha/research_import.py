"""Turning a research result into Akasha drafts, and accepting them -- pure.

No database, no HTTP: functions from data to data, so every rule about what
lands where can be tested on its own. ``research_service`` does the reading
and writing around them.

Where things go, in the world the research was requested in:

- ``research-inbox`` holds each draft and the *new* sources it cites, all
  ``status: unverified``, authored by ``research-bot``. Nothing in the inbox
  is canon.
- A **refinement** that replaces a pending draft takes over its slug, so the
  draft's history holds both versions, and keeps the inbox sources it still
  cites; the rest of the old draft's inbox sources go.
- **Accept** moves the draft to ``research`` and its sources to ``sources``,
  ``status: verified``, authored by the writer who accepted. A source whose
  URL ``sources`` already holds is not duplicated: the draft is relinked to it.

Akasha documents are flat, so the nested parts of a result -- facts with their
second-check verdicts, dropped facts, image candidates -- travel in the job
record (``details``), and the documents carry what reads well as an article.
"""

import re
from dataclasses import dataclass, field
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

INBOX = "research-inbox"
RESEARCH = "research"
SOURCES = "sources"
BOT = "research-bot"

MAX_TITLE = 300
MAX_BODY = 60_000
MAX_FACTS = 100
MAX_SOURCES = 30
MAX_IMAGES = 10
_CITE = re.compile(r"\[\[cite:(s\d+)\]\]")
_TRACKING = re.compile(r"^(utm_|fbclid$|gclid$|mc_|ref$|ref_src$)")


class InvalidResult(ValueError):
    """The worker's result does not have the shape the contract promises."""


# -- small, shared rules -------------------------------------------------------


def slugify(text: str) -> str:
    """The shared front-end ``slugify`` (static/js/slug.js), in Python."""
    lowered = str(text or "").lower().replace("'", "").replace("’", "")
    return re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")


def unique_slug(base: str, taken: set[str], fallback: str, limit: int = 60) -> str:
    """``base`` as a slug no one holds, adding -2, -3… if needed; recorded in taken."""
    stem = (slugify(base)[:limit].strip("-")) or fallback
    slug, n = stem, 2
    while slug in taken:
        slug = f"{stem}-{n}"
        n += 1
    taken.add(slug)
    return slug


def normalize_url(url: str) -> str:
    """One spelling per page: what deduplicates sources.

    Lower-case scheme and host, no default port, no fragment, no trailing
    slash, tracking parameters dropped and the rest sorted.
    """
    parts = urlsplit(url.strip())
    host = (parts.hostname or "").lower().removeprefix("www.")
    port = parts.port
    if port and not ((parts.scheme == "http" and port == 80)
                     or (parts.scheme == "https" and port == 443)):
        host = f"{host}:{port}"
    query = sorted((k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
                   if not _TRACKING.match(k))
    path = parts.path.rstrip("/") or ""
    return urlunsplit((parts.scheme.lower(), host, path, urlencode(query), ""))


# -- validating what the worker sent -------------------------------------------


def _text(value, name, *, limit=None, empty=False):
    if not isinstance(value, str) or (not empty and not value.strip()):
        raise InvalidResult(f"{name} must be text")
    return value[:limit] if limit else value


def _web_url(value, name):
    _text(value, name)
    if urlsplit(value).scheme not in ("http", "https") or len(value) > 2048:
        raise InvalidResult(f"{name} must be an http(s) URL")
    return value


def validate_result(result) -> dict:
    """A normalised copy of a research result, or ``InvalidResult``.

    Strict about shape -- this is data from another machine -- and defensive
    about the one rule the design puts on Akasha too: a fact without a
    citation to a known source is not imported as a fact.
    """
    if not isinstance(result, dict):
        raise InvalidResult("the result must be an object")
    article = result.get("article")
    if not isinstance(article, dict):
        raise InvalidResult("article must be an object")
    raw_sources = result.get("sources")
    if not isinstance(raw_sources, list) or len(raw_sources) > MAX_SOURCES:
        raise InvalidResult("sources must be a list of at most 30")
    sources = []
    for n, source in enumerate(raw_sources):
        if not isinstance(source, dict):
            raise InvalidResult(f"sources[{n}] must be an object")
        key = _text(source.get("key"), f"sources[{n}].key")
        if not re.fullmatch(r"s\d+", key):
            raise InvalidResult(f"sources[{n}].key is not a source key")
        excerpts = source.get("excerpts") or []
        if not isinstance(excerpts, list) or not all(isinstance(e, str) for e in excerpts):
            raise InvalidResult(f"sources[{n}].excerpts must be a list of text")
        sources.append({
            "key": key,
            "url": _web_url(source.get("url"), f"sources[{n}].url"),
            "title": _text(source.get("title"), f"sources[{n}].title", limit=MAX_TITLE),
            "site": _text(source.get("site", ""), f"sources[{n}].site", limit=200,
                          empty=True),
            "language": _text(source.get("language", ""), f"sources[{n}].language",
                              limit=20, empty=True),
            "retrieved_at": _text(source.get("retrieved_at", ""), "retrieved_at",
                                  limit=40, empty=True),
            "excerpts": [e[:2000] for e in excerpts[:20]],
        })
    keys = {s["key"] for s in sources}

    facts, dropped = [], []
    raw_facts = article.get("facts")
    if not isinstance(raw_facts, list):
        raise InvalidResult("article.facts must be a list")
    for n, fact in enumerate(raw_facts[:MAX_FACTS]):
        if not isinstance(fact, dict):
            raise InvalidResult(f"facts[{n}] must be an object")
        text = _text(fact.get("text"), f"facts[{n}].text", limit=1000)
        citations = [c for c in fact.get("citations") or []
                     if isinstance(c, dict) and c.get("source") in keys
                     and isinstance(c.get("quote"), str) and c["quote"].strip()]
        if not citations:
            dropped.append({"text": text, "reason": "no_citation"})
            continue
        status = (fact.get("check") or {}).get("status")
        facts.append({"text": text,
                      "citations": [{"source": c["source"], "quote": c["quote"][:2000]}
                                    for c in citations],
                      "check": status if status in ("supported", "partial")
                      else "unchecked"})
    for item in result.get("dropped_facts") or []:
        if isinstance(item, dict) and isinstance(item.get("text"), str):
            dropped.append({"text": item["text"][:1000],
                            "reason": str(item.get("reason", ""))[:40]})

    images = []
    for n, image in enumerate((article.get("image_candidates") or [])[:MAX_IMAGES]):
        if not isinstance(image, dict) or image.get("source") not in keys:
            continue
        license_ = image.get("license")
        images.append({
            "url": _web_url(image.get("url"), f"image_candidates[{n}].url"),
            "caption": _text(image.get("caption", ""), "caption", limit=300,
                             empty=True),
            "license": license_[:300] if isinstance(license_, str) else None,
            "source": image["source"],
            "fetch_token": _text(image.get("fetch_token"), "fetch_token", limit=100),
        })

    verification = result.get("verification") or {}
    status = verification.get("status")
    if status not in ("checked", "skipped", "off"):
        raise InvalidResult("verification.status is not a known outcome")
    links = [ref for ref in article.get("links") or []
             if isinstance(ref, str) and re.fullmatch(r"[^/\s]+/[^/\s]+/[^/\s]+", ref)]
    return {
        "title": _text(article.get("title"), "article.title", limit=MAX_TITLE),
        "body": _text(article.get("body", ""), "article.body", limit=MAX_BODY,
                      empty=True),
        "topic": _text(article.get("topic", ""), "topic", limit=60, empty=True),
        "era": _text(article.get("era", ""), "era", limit=120, empty=True),
        "facts": facts,
        "dropped": dropped,
        "sources": sources,
        "images": images,
        "links": links[:20],
        "verification": {"status": status,
                         "model": verification.get("model"),
                         "checked": verification.get("checked", 0),
                         "removed": verification.get("removed", 0)},
        "model": _text(result.get("model", ""), "model", limit=100, empty=True),
        "generated_at": _text(result.get("generated_at", ""), "generated_at",
                              limit=40, empty=True),
    }


# -- importing -----------------------------------------------------------------


@dataclass
class ImportPlan:
    draft_slug: str
    draft: dict
    new_sources: list[tuple[str, dict]] = field(default_factory=list)
    details: dict = field(default_factory=dict)
    # Inbox sources of a replaced draft, rewritten from the new result.
    reused_sources: list[tuple[str, dict]] = field(default_factory=list)


def plan_import(result: dict, *, question: str, job_id: str,
                accepted_sources: dict[str, str], taken: set[str],
                reuse: dict[str, str] | None = None,
                draft_slug: str | None = None) -> ImportPlan:
    """Documents for the inbox from a validated result.

    ``accepted_sources`` maps normalised URL -> slug in ``sources``; those are
    linked to, not copied. ``taken`` holds every slug in use in the inbox (and
    in ``research``, so an accepted draft can keep its name); new ones are
    added to it.

    Replacing a draft, ``draft_slug`` is its slug and ``reuse`` maps normalised
    URL -> slug of its inbox sources: a source found again keeps its document.
    """
    reuse = reuse or {}
    refs, new_sources, reused, source_rows = {}, [], [], []
    for source in result["sources"]:
        url = normalize_url(source["url"])
        known = accepted_sources.get(url)
        if known:
            refs[source["key"]] = f"{SOURCES}/{known}"
        elif url in reuse:
            refs[source["key"]] = f"{INBOX}/{reuse[url]}"
            reused.append((reuse.pop(url), _source_document(source, job_id)))
        else:
            slug = unique_slug(f"{source['site']} {source['title']}", taken, "source")
            refs[source["key"]] = f"{INBOX}/{slug}"
            new_sources.append((slug, _source_document(source, job_id)))
        source_rows.append({"key": source["key"], "ref": refs[source["key"]],
                            "url": source["url"], "title": source["title"],
                            "new": not known})

    draft_slug = draft_slug or unique_slug(result["title"], taken,
                                           f"research-{job_id[-8:]}")
    body = _CITE.sub(lambda m: f"[[{refs[m.group(1)]}]]" if m.group(1) in refs else "",
                     result["body"]).strip()
    if result["links"]:
        body += "\n\n== Related ==\n" + "\n".join(f"* [[{ref}]]" for ref in result["links"])
    draft = {
        "title": result["title"],
        "body": body,
        "status": "unverified",
        "question": question,
        "generated_by": result["model"],
        "generated_at": result["generated_at"],
        "verification": result["verification"]["status"],
        "sources": [refs[s["key"]] for s in result["sources"]],
        "research_job": job_id,
    }
    for name in ("topic", "era"):
        if result[name]:
            draft[name] = result[name]
    partial = [f["text"] for f in result["facts"] if f["check"] == "partial"]
    if partial:
        draft["partial_facts"] = partial
    if result["dropped"]:
        draft["dropped_facts"] = [f"{d['reason']}: {d['text']}" for d in result["dropped"]]

    details = {
        "facts": [{"text": f["text"], "check": f["check"],
                   "citations": [{"source": refs[c["source"]], "quote": c["quote"]}
                                 for c in f["citations"]]}
                  for f in result["facts"]],
        "dropped_facts": result["dropped"],
        "sources": source_rows,
        "images": [{**{k: image[k] for k in ("url", "caption", "license",
                                             "fetch_token")},
                    "source": refs[image["source"]], "imported": None}
                   for image in result["images"]],
        "verification": result["verification"],
        "links": result["links"],
    }
    return ImportPlan(draft_slug=draft_slug, draft=draft, new_sources=new_sources,
                      details=details, reused_sources=reused)


def _source_document(source: dict, job_id: str) -> dict:
    document = {"title": source["title"], "url": source["url"], "kind": "source",
                "status": "unverified", "research_job": job_id,
                "excerpts": source["excerpts"]}
    for name in ("site", "language", "retrieved_at"):
        if source[name]:
            document[name] = source[name]
    return document


# -- accepting -----------------------------------------------------------------


@dataclass
class AcceptPlan:
    article_slug: str
    article: dict
    moves: list[tuple[str, str, dict]]   # (inbox slug, sources slug, document)
    relinked: dict[str, str]             # inbox slug -> existing sources slug


def plan_accept(draft: dict, inbox_sources: dict[str, dict], *, writer: str,
                accepted_at: str, accepted_sources: dict[str, str],
                taken_research: set[str], taken_sources: set[str],
                draft_slug: str) -> AcceptPlan:
    """What accepting ``draft`` writes: the article, and its sources moved.

    ``inbox_sources`` are the draft's own inbox sources (slug -> document) --
    possibly edited by the writer since import. A source whose URL is now in
    ``sources`` (accepted from another draft meanwhile) is relinked rather
    than duplicated. The draft's slug is kept when ``research`` has it free.
    """
    mapping, moves, relinked = {}, [], {}
    for slug, document in inbox_sources.items():
        existing = accepted_sources.get(normalize_url(document.get("url", "")))
        if existing:
            mapping[slug] = existing
            relinked[slug] = existing
            continue
        target = slug if slug not in taken_sources else unique_slug(
            slug, taken_sources, "source")
        taken_sources.add(target)
        mapping[slug] = target
        moves.append((slug, target, {**document, "status": "verified",
                                     "verified_by": writer,
                                     "verified_at": accepted_at}))

    def relink(text: str) -> str:
        for slug, target in mapping.items():
            text = text.replace(f"[[{INBOX}/{slug}]]", f"[[{SOURCES}/{target}]]")
            text = text.replace(f"[[{INBOX}/{slug}|", f"[[{SOURCES}/{target}|")
        return text

    article = {**draft, "status": "verified", "verified_by": writer,
               "verified_at": accepted_at, "drafted_by": BOT}
    article["body"] = relink(draft.get("body", ""))
    article["sources"] = [
        f"{SOURCES}/{mapping[ref.split('/', 1)[1]]}"
        if ref.startswith(f"{INBOX}/") and ref.split("/", 1)[1] in mapping else ref
        for ref in draft.get("sources") or []]
    slug = draft_slug if draft_slug not in taken_research else unique_slug(
        draft_slug, taken_research, "research")
    return AcceptPlan(article_slug=slug, article=article, moves=moves, relinked=relinked)
