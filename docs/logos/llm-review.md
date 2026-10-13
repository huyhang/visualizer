# LLM review

An LLM review is a second reader for one draft of one section. It's a model
on the GPU box ([`docs/gpu_worker`](../gpu_worker/README.md)) that checks the
prose for three things:

- **continuity** against your canon;
- **anachronism** against your verified research and the anachronism
  watchlist;
- **prose**: clarity, rhythm, redundancy.

It reports issues anchored to a block and a verbatim quote, and you work
through them. Only the API exists so far; there is no UI yet. The Writing
Coach's deterministic rules are unchanged and still send nothing anywhere.

LLM review is off unless `GPU_WORKER_URL` is set. When it is off,
`GET /llm-review/availability` says so and asking for a review answers 503.
For a box that never sleeps, run `python -m visualizer.devserver
--fake-gpubox`.

## The routes

All of these live under one section and need **write on the book**. A review
is private feedback on unpublished prose, so the book's read-only
collaborators can't see it.

```
GET    /llm-review/availability                          off, asleep, busy or ready
GET    …/sections/<section>/reviews/references           preview what would be sent
POST   …/sections/<section>/reviews                      ask         202  LlmReview
GET    …/sections/<section>/reviews                      recent           LlmReviewList
GET    …/sections/<section>/reviews/<id>                 follow           LlmReview
DELETE …/sections/<section>/reviews/<id>                 cancel           LlmReview
PUT    …/sections/<section>/reviews/<id>/issues/<issue>  {"status": "open|dismissed|resolved"}
```

`…` is `/books/<book>/volumes/<volume>`. The request body accepts these
fields, all optional:

| Field | Meaning | Default |
|---|---|---|
| `draft` | Which draft to review | the primary |
| `checks` | Any of `continuity`, `anachronism`, `prose` | all three |
| `dialect` | `en-US` or `en-GB` | `en-US` |
| `verify` | `auto`, `required` or `off`: whether a second machine re-judges each issue | `auto` |
| `include` | Up to 20 more Akasha articles to send, as `database/collection/id` | none |

The exact shapes are in [`openapi.json`](openapi.json).

## What is sent

**The chapter:** the draft's text, one entry per non-empty block, with the
block's stable id. That's the text the reader shows, mentions and links
included.

**The references**, in this order:

1. **Deviations**: every article in the book world's `deviations` collection.
   A deviation says "this is on purpose", and the box never reports against
   one. Deviations go first, so they are never the references that get cut.
2. **The anachronism watchlist**: every article in the world's `watchlist`
   collection.
3. **What the chapter mentions or links**, in reading order, then whatever you
   `include`:
   - articles in `research` are sent only once their status is `verified`, so
     an unchecked AI draft never becomes the standard the prose is held to;
   - nothing from `research-inbox` or `sources` is sent;
   - everything else is canon.

Only articles you could open yourself are sent. Each is sent as its fields
(`Eyes: grey`) and then its body, cut to 1,500 characters, and at most 40
are sent. That's exactly what the box reads, so nothing is sent that it would
ignore. Provenance fields of research articles, such as `dropped_facts`, are
left out, because they are not facts.

`GET …/reviews/references` shows that list, plus everything left out and why:
`unavailable` (missing, or not yours to read), `unverified`,
`unreviewed_research`, `source` or `over_limit`. A review records the same
two lists. It records refs and titles only, not the text.

## The issues

A review becomes `done` the first time a poll finds the box finished. The
issues are stored once, however many tabs are polling. Each issue has:

- `check`, `severity` (`info` / `warning`) and `confidence` (`possible` /
  `likely`);
- `block` and `quote`: the quote appears verbatim in that block, a rule the
  box enforces;
- `message` and `suggestion`;
- `reference`: the article the issue is based on, `null` for prose issues;
- `verified`: `true` when a second machine confirmed it, `null` when there
  was no second check;
- `status`: `open`, `dismissed` or `resolved`, which you set.

Each issue also repeats itself in the Writing Coach's finding shape
(`category`, `title`, `excerpt`, `replacement`), so one panel can show both.

Issues are shown against the draft **as it is now**. An issue is `stale`
when its quote is no longer in its block, which means you have already changed
the passage. A review of an older revision says `outdated: true`.

## Privacy

- The chapter goes to the box on your own hardware. Logos doesn't store it,
  and the box erases it when the job ends.
- What Logos keeps is the review record: settings, the refs and titles sent,
  and the issues. The issues quote a few of your words.
- Each section keeps only its ten newest finished reviews.
- Reviews are deleted with their book (`purge_book`) and with the account
  that asked for them (`purge_user`).

Each writer can have 3 reviews running at once, and the whole stack 10.
Beyond that, asking returns 429 with `Retry-After`.
