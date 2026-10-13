# Research

A writer asks a question about the real world, such as "How was tea served
in the Song dynasty?". The AI worker on the GPU box
([`docs/gpu_worker`](../gpu_worker/README.md)) searches the web and writes a
cited article. The article lands in the world as a **draft** that nobody
treats as canon until a writer accepts it. Only the API exists so far; there
is no UI yet.

Research is off unless `GPU_WORKER_URL` is set (see the gpu_worker README).
When it is off, `GET /research/availability` says so, and every other
research route answers 503 without recording anything. For a box that never
sleeps, run `python -m visualizer.devserver --fake-gpubox`.

## The flow

```
POST   /databases/<world>/research/jobs                  ask         202  ResearchJob
GET    /databases/<world>/research/jobs                  recent jobs      ResearchJobList
GET    /databases/<world>/research/jobs/<id>             follow           ResearchJob
DELETE /databases/<world>/research/jobs/<id>             cancel           ResearchJob
GET    /databases/<world>/research/inbox                 drafts awaiting review
GET    /databases/<world>/research/inbox/<draft>         draft + facts, sources, images
POST   /databases/<world>/research/inbox/<draft>/accept  accept           ResearchAccepted
POST   /databases/<world>/research/inbox/<draft>/reject  reject      204
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
| Ask, cancel, reject, import an image | write on `research-inbox` |
| Accept | write on `research-inbox`, `research` and `sources` |

A world's owner has all of these. Each writer can have 3 jobs running at once,
and the whole Akasha 10. Beyond that, asking returns 429 with
`Retry-After: 60`.

## Decisions taken

- **One inbox per world.** Drafts live in the world the question was asked
  in, not in a shared space.
- **Accepting moves documents, not copies them.** After a decision the inbox
  holds nothing for that draft.
- **Pending drafts don't share sources.** Two drafts citing the same new URL
  each get their own inbox copy. Accept de-duplicates against `sources`, so
  the second draft accepted is relinked to the first one's source.
