# Research

A writer asks a question about the real world, such as "How was tea served
in the Song dynasty?". The AI worker on the GPU box
([`docs/gpu_worker`](../gpu_worker/README.md)) searches the web and writes a
cited article. The article lands in the world as a **draft** that nobody
treats as canon until a writer accepts it, or takes parts of it into a
research note.

Writers use it through the **research studio**, `/studio/<world>` (see
[The studio](#the-studio) below), reached from the **✦ Research** button on a
world's page. Everything the studio does is also an API route.

Research is off unless `GPU_WORKER_URL` is set (see the gpu_worker README).
When it is off, `GET /research/availability` says so, and every other
research route answers 503 without recording anything. For a box that never
sleeps, run `python -m visualizer.devserver --fake-gpubox`.

## The studio

One page per world, in three panes:

- **Topics.** An ask box, the GPU box's state, and the world's lines of
  inquiry as a tree: each question, and the sub-topics dug out of it. Each
  topic shows whether it is researching, waiting for its plan to be checked,
  ready to read, or saved to notes. Below the tree are the world's research
  notes.
- **Draft.** While a job runs, a timeline of its stages. If the writer asked
  to check the plan first, the proposed searches are shown, editable, before
  any page is read. Once the job is done, the draft reads like an article.
  Each citation opens its source and the exact words taken from it. Every
  paragraph and fact offers **Add** (to the note), **Dig deeper**, and
  **Distrust** (research again without that source). Tabs show the facts with
  their second-check verdicts, the sources, the image candidates, and the
  facts that were dropped and why. A picture whose preview the box can no
  longer fetch is marked as gone and can't be added. **Steer** refines the
  draft with feedback. A steer of a question asked with the plan check on
  stops for its searches too, since the box keeps the draft's settings; the
  plan is shown over the draft to approve or cancel. **Keep as note** accepts
  the whole draft as it stands into `research`. **Done with it** closes the
  draft. **Discard** turns it down. Each of the last three asks first.
- **Note.** The note being written, either a new one or an existing note from
  `research`. What is added keeps its citations. Blocks can be edited
  (wikitext), reordered and removed, and the writer can add their own words.
  **Save** imports the chosen images, then saves the note. Anything added
  while it saves stays in the composer for the next save. A picture that
  can't be imported is named in the error, and the ones imported before it
  are not imported again.

On a narrow screen the panes become three tabs. The note being composed is
kept in the browser, so a reload does not lose it. On a stack with no GPU box,
or for a writer who can't read the world's research, the studio is one screen
saying so, not three panes of errors.

The studio is built with React, TypeScript and Vite in `frontend/`, and is
compiled into `static/studio/`. Until it is compiled, the page explains how
to compile it. `docker/smoke_research_studio_ui.py` walks a writer's whole
loop in a real browser.

## The flow

```
POST   /databases/<world>/research/jobs                  ask         202  ResearchJob
GET    /databases/<world>/research/jobs                  recent jobs      ResearchJobList
GET    /databases/<world>/research/jobs/<id>             follow           ResearchJob
DELETE /databases/<world>/research/jobs/<id>             cancel           ResearchJob
POST   /databases/<world>/research/jobs/<id>/plan        approve plan     ResearchJob
GET    /databases/<world>/research/inbox                 drafts awaiting review
GET    /databases/<world>/research/inbox/<draft>         draft + facts, sources, images
POST   /databases/<world>/research/inbox/<draft>/accept  accept           ResearchAccepted
POST   /databases/<world>/research/inbox/<draft>/reject  reject      204
POST   /databases/<world>/research/inbox/<draft>/refine  refine      202  ResearchJob
POST   /databases/<world>/research/inbox/<draft>/done    close       204
POST   /databases/<world>/research/notes                 save a note 201/200  ResearchNoteSaved
GET    /databases/<world>/research/inbox/<draft>/images/<n>?size=preview|full
POST   /databases/<world>/research/inbox/<draft>/images/<n>/import          201  Media
```

The exact shapes are in [`openapi.json`](openapi.json).

1. **Ask.** Akasha validates the request and records a job in the reserved
   `_research` database. It sends the box the question plus the refs and
   titles of up to 200 articles in the world, so the box can link to them.
   It never sends article bodies. A job the box has already finished still
   reads `running` until the first poll settles it.
2. **Follow.** Each `GET` of a job asks the box how far it has got. If the box
   is asleep or busy, the job reports its last known state. The first poll
   that finds the job done imports the result. An atomic claim makes sure the
   import runs only once, however many tabs are polling. A result that fails
   validation or can't be stored leaves nothing behind, and the job fails with
   `invalid_result` or `import_failed`. If the box forgot the job before anyone
   polled, the job fails with `expired`.
3. **Import.** The draft and any sources the world doesn't already have go
   into `research-inbox`. They are marked `status: unverified` and written by
   `research-bot`, an account that can't log in and holds read/write on the
   inbox only. A source whose URL is already in `sources` (after normalising,
   e.g. dropping tracking parameters) is cited from there instead. Documents
   must be flat, so the nested parts travel in the job record instead: facts
   with their second-check verdicts, dropped facts, image candidates and
   their fetch tokens.
4. **Review.** **Accept** moves the draft to `research` and its new sources to
   `sources`. They become `status: verified` and are owned and written by the
   writer who accepted. The draft's citations are rewritten to point at the
   new refs. **Reject** deletes the draft and its new sources. The delete is
   soft: their history stays. Either decision is final, and deciding again
   returns 409.

## Steering a job

**Approving the plan.** Ask with `"approve_plan": true` and the job stops
after the box has planned its searches, in `awaiting_approval`. The proposed
queries are on the job as `plan.queries`. `POST …/jobs/<id>/plan` with
`{"queries": [...]}` (at most 6, each `{q, language}`) lets it go on with
the queries as given, edited or not. To turn a plan down, cancel the job.
While it waits, the job holds no GPU time but still counts against the job
limits. If nobody approves it within a day (`PLAN_TTL_HOURS` on the box), it
fails with `plan_expired`.

**Refining a draft.** `POST …/inbox/<draft>/refine` with
`{"feedback": "…", "exclude_sources": ["research-inbox/…"]}` researches a
pending draft again:

- The box gets the draft's question and settings, and you can change any
  setting except the question in the same body. It also gets the facts the
  draft found, your feedback, the sources to keep, and the URLs never to read
  again. Excluded URLs include any that an earlier refinement of the draft
  excluded.
- The box fetches the kept sources again and checks every quote anew; nothing
  is trusted from the old draft. It searches for more sources to fill
  `max_sources`, which defaults to the kept sources plus 4.
- Your feedback reaches the box's search planner, so it can end up in web
  searches, just like the question.
- If the draft is still pending when the result arrives, the result
  **replaces it under the same slug**. It's saved as a new version, so the
  draft's history can diff the two. Sources found again keep their inbox
  documents, and the sources the new version no longer cites are deleted. The
  old job's `review` becomes `superseded`, and its `superseded_by` names the
  refinement.
- If you accept, reject or delete the draft while it's being refined, the
  refinement arrives as a separate new draft.
- A draft can have only one refinement running at a time (409 otherwise). A
  draft's detail and its inbox row show when one is running.

## Digging deeper

A question asked with `"parent": "<job id>"` digs deeper from that job: the
studio draws it under its parent in the topic tree. The parent must be a job
in the same world. The link is Akasha's alone and never reaches the box,
which sees an ordinary question. A refinement inherits its draft's parent, so
a steered topic keeps its place, and children follow it: a parent that was
superseded is read along its `superseded_by` chain.

`GET …/jobs?limit=<n>` (1–200, default 50) lists more jobs, which the studio
needs in order to draw the tree.

The studio pre-fills the sub-topic's question from the passage and the parent
topic's question. Akasha has no model of its own, so that wording is a
template, which the writer edits. The question is still the only text the box
searches with, and is cut to fit its 500 characters.

## Notes from drafts

`POST …/research/notes` saves a note the writer composed:

```json
{"title": "Song tea", "body": "Tea was whisked [[research-inbox/museum-tea]].",
 "drafts": ["research-inbox/song-tea"]}
```

Add `"note": "<slug>", "rev": <n>` to update an existing note in `research`
instead of creating one.

- **Only what the note cites is accepted.** Every
  `[[research-inbox/<slug>]]` in the body must be a source of an open draft.
  Each one is moved to `sources` as `status: verified`, verified by the
  writer, and the note is relinked to it. A source whose URL `sources`
  already holds is linked to rather than copied. A link to anything else in
  the inbox, such as a draft or a source no open draft cites, is refused
  with 400.
- **The drafts stay open.** A draft whose sources a note accepted is relinked
  to them, in its body, in its sources list and in the job's detail, so one
  draft can feed several notes. Each job records the notes it fed (`notes`):
  those whose sources the note took, plus the `drafts` named.
- **An update is checked first.** The note's revision is compared before
  anything is written, so a note changed meanwhile answers 409 and nothing
  moves. If the note cannot be written in the last instant, the sources
  created for it are deleted again.
- **A new note** gets a slug from its title in `research`, `status: verified`,
  and its sources listed. **An updated note** keeps its other fields, and its
  `sources` list grows.

`POST …/inbox/<draft>/done` closes a draft the writer has finished with. It
deletes the draft and the inbox sources it still holds, like reject. The
difference is that the job's review becomes `done`, not `rejected`, so the
topic reads as used rather than turned down. Sources notes already accepted
are no longer in the inbox, so they stay.

## Images

The worker suggests image candidates, each with a URL, caption, license and
source, plus a `fetch_token`. Only the box fetches from the web. The token is
an HMAC that only the box can make, so Akasha can't use the box to fetch an
arbitrary URL. Akasha keeps the tokens in the job record and never shows them
to clients.

- **Preview** (`GET …/images/<n>`) proxies the box's image, 360 px by default
  (`?size=full` for the original). The response carries
  `Cache-Control: private`.
- **Import** (`POST …/images/<n>/import`) runs the full image through the
  ordinary media pipeline: size caps, derivatives and metadata stripping. The
  resulting media keeps `source_url` and `license`, and its alt text is the
  caption. The draft records which media each candidate became.

An image that has vanished from the web returns 502.

## Who may do what

| Action | Needs |
|---|---|
| Read jobs, the inbox, drafts, image previews | read on `research-inbox` |
| Ask, cancel, approve a plan, refine, reject, close, import an image | write on `research-inbox` |
| Accept | write on `research-inbox`, `research` and `sources` |
| Save a new note | write on `research-inbox` and `sources`, create on `research` |
| Add to an existing note | write on `research-inbox` and `sources`, and on that note |

A world's owner has all of these. Each writer can have 3 jobs running at once,
and the whole Akasha 10. Beyond that, asking returns 429 with
`Retry-After: 60`.

## Decisions taken

- **One inbox per world.** Drafts live in the world the question was asked
  in, not in a shared space.
- **Accepting moves documents, not copies them.** After a decision the inbox
  holds nothing for that draft.
- **A refinement replaces its draft instead of sitting next to it.** One draft
  per question in the inbox, with the earlier versions kept in its history.
- **Notes are composed, or a draft is kept whole.** A writer takes passages,
  facts and images from any drafts into a new note or an existing one. A
  draft good enough as it stands is kept whole with **Keep as note**, which
  is `accept`.
- **Digging deeper starts a new topic.** The draft it came from stays as it
  is. Revising a draft in place is refining.
- **The studio is a compiled surface.** It is Akasha's first page built with
  React and Vite, compiled into static files at build time, so the NAS still
  runs no Node and loads nothing from outside.
- **Pending drafts don't share sources.** Two drafts citing the same new URL
  each get their own inbox copy. Accept de-duplicates against `sources`, so
  the second draft accepted is relinked to the first one's source.
