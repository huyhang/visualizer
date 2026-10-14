# GPU-box AI worker — API (v1)

The contract between the visualizer stack and the AI worker on the RTX 3090 box.
**Akasha** submits `research` jobs and **Logos** submits LLM `review` jobs, and
`discussion` jobs when a writer answers one of a review's issues; neither talks
to Ollama or SearXNG, which stay bound to the box's localhost behind the
worker.

**Status: built; not yet run on the real box.** The research and review
pipelines run on local models (smoke-tested end to end on a laptop with
`granite4.2:8b`, a local SearXNG and the open web; see *Smoke testing* below).
The discussion pipeline, added later, has so far run only against a scripted
model in the tests.
This document and [`openapi.json`](openapi.json) (OpenAPI 3.1) are what
both sides are written and tested against -- the worker validates against the
JSON file at runtime -- so if the two disagree, fix one of them.

```
NAS (visualizer stack)                     GPU box
┌────────────────────────┐                ┌──────────────────────────────────┐
│ Logos  ─ review jobs ──┼──┐             │ tailscale serve :8443 (HTTPS)    │
│ Akasha ─ research jobs ┼──┼─ Tailscale ─┼──▶ worker 127.0.0.1:8700         │
└────────────────────────┘  │ + token     │      ├──▶ Ollama   (localhost)   │
                            │             │      ├──▶ SearXNG  (localhost)   │
                            │             │      └──▶ verifier (optional Mac)│
                            └─────────────┴──────────────────────────────────┘
```

**Decisions that shape the API:**

- **One worker, one queue.** Research, reviews and discussions share
  authentication, health checks, the job store and GPU scheduling.
- **Everything is an async job.** A chapter review can take 30–90 s — longer than
  typical reverse-proxy timeouts (Synology's default is ~60 s).
- **The NAS stack never depends on it.** With no worker configured, or the box
  asleep, every service keeps working; the AI features report themselves
  unavailable.
- **The second checker is optional.** When a second machine (the M1 Max) is up, the
  worker asks it narrow yes/no questions and results say so; when it isn't, the
  stage is skipped and results say that instead.

## In this repo

| What | Where |
|---|---|
| The client every service shares: config, HTTP, errors, availability | `src/visualizer/gpubox/` |
| A fake box that keeps this contract, for tests and the dev server | `src/visualizer/gpubox/fake.py` |
| Akasha's research seam, and `GET /research/availability` | `src/visualizer/akasha/research.py`, `research_routes.py` |
| Wiring: a worker is used only when `GPU_WORKER_URL` is set | `src/visualizer/stack.py` |
| Tests holding the client, the fake and this spec together | `tests/gpubox/` |
| **The worker itself** -- runs on the box, imports nothing from the stack | `src/visualizer/gpu_worker/` |
| Its image, and the box's compose file (worker + SearXNG) | `docker/Dockerfile.worker`, `docker/gpubox/` |
| The worker's tests, and the end-to-end test against the stack's client | `tests/gpu_worker/` |

**Switching it on** — in `docker/.env`, then redeploy:

```
GPU_WORKER_URL=https://gpubox.<your-tailnet>.ts.net:8443
GPU_WORKER_TOKEN=<the worker's WORKER_TOKEN>
```

Optional: `GPU_WORKER_TIMEOUT` (seconds, default 10). A URL without a token stops
the app at startup. Until the box exists, `python -m visualizer.devserver
--fake-gpubox [MODE]` puts a fake one behind the features, in any state a writer
can meet.

## Running the worker on the box

> Not yet run on the real machine. These steps follow the design notes; expect
> small adjustments for your driver, Docker and Tailscale versions.

**Prerequisites:** Ubuntu Server with the NVIDIA driver, Tailscale and UFW; Docker
with the NVIDIA Container Toolkit; Ollama installed natively (not in Docker).

1. **Ollama**: one big model at a time, unloaded when idle so ComfyUI can have the
   GPU back. `sudo systemctl edit ollama`, then `sudo systemctl restart ollama`:

   ```
   [Service]
   Environment="OLLAMA_MAX_LOADED_MODELS=1"
   Environment="OLLAMA_NUM_PARALLEL=1"
   Environment="OLLAMA_KEEP_ALIVE=10m"
   Environment="OLLAMA_FLASH_ATTENTION=1"
   Environment="OLLAMA_KV_CACHE_TYPE=q8_0"
   ```

   Then `ollama pull qwen3:30b`. The worker reaches Ollama on localhost, so it
   needs no `OLLAMA_HOST` change. Keep any you already made for Mac apps, behind
   the UFW rule that allows only `tailscale0`.

2. **Configure**, from a clone of this repository on the box:

   ```bash
   cp docker/gpubox/.env.example docker/gpubox/.env
   # set WORKER_TOKEN and SEARXNG_SECRET: openssl rand -hex 32 for each
   docker compose -f docker/gpubox/compose.yml up -d --build
   ```

3. **Expose it to the tailnet only, with HTTPS.** In the Tailscale admin console,
   enable MagicDNS and HTTPS certificates, then:

   ```bash
   sudo tailscale serve --bg --https=8443 http://127.0.0.1:8700
   ```

   Access controls: tag the NAS `tag:nas` and the box `tag:gpubox`, then allow
   `tag:nas` → `tag:gpubox:8443`. Adding rules removes Tailscale's default
   allow-all, so keep one for your own devices.

4. **Point the NAS at it.** Install Tailscale on the NAS (Package Center), set
   `GPU_WORKER_URL` and `GPU_WORKER_TOKEN` in the visualizer's `docker/.env` (the
   token is the box's `WORKER_TOKEN`), and redeploy. If research then reports the
   box unreachable while it is up, the container can't resolve MagicDNS: see the
   `extra_hosts` note in `docker/docker-compose.nas.yml`.

5. **Check**, from the NAS:

   ```bash
   curl -s -H "Authorization: Bearer $GPU_WORKER_TOKEN" \
     https://gpubox.<your-tailnet>.ts.net:8443/v1/health
   ```

   `ok: true` means Ollama and SearXNG are up. Akasha's
   `GET /research/availability` should then say `cold` or `ready`.

**Updating:** `git pull && docker compose -f docker/gpubox/compose.yml up -d --build worker`.
The job store lives in the `worker-data` volume and survives rebuilds; a job
running at the time is failed as interrupted.

**Logs** (`docker compose -f docker/gpubox/compose.yml logs -f worker`) carry job
metadata only -- ids, kinds, outcomes, timings -- never prose, questions or
results.

**Smoke testing.** Unit tests pin down what the pipelines do with model
output; only a real model shows whether the prompts work. To try them on a
laptop: run Ollama with any instruction model, start SearXNG with
`docker/gpubox/searxng/settings.yml`, and run the worker **in a container** --
a sandbox or corporate proxy that forces traffic through `HTTPS_PROXY` will
block the fetcher, which deliberately connects straight to the address it
checked and never through a proxy. On a laptop with `granite4.2:8b`, a
three-source research job took under three minutes; quotes the model
invented were dropped as `quote_not_found`, as designed. Expect `qwen3:30b` on
the 3090 to drop fewer.

**On a laptop**, without Docker or a GPU, to exercise the real HTTP path from the
dev server:

```bash
export WORKER_TOKEN=$(openssl rand -hex 32)
python -m visualizer.gpu_worker &                        # 127.0.0.1:8700
GPU_WORKER_URL=http://127.0.0.1:8700 GPU_WORKER_TOKEN=$WORKER_TOKEN \
  python -m visualizer.devserver
```

## Conventions

| Aspect | Rule |
|---|---|
| Base URL | `https://gpubox.<your-tailnet>.ts.net:8443/v1` |
| Auth | `Authorization: Bearer <WORKER_TOKEN>` on every request; missing/invalid → `401` |
| Format | JSON, UTF-8. Timestamps are ISO 8601 UTC |
| Idempotency | `POST /jobs` accepts `Idempotency-Key`; repeating a key returns the original job (`200`) instead of creating a new one. Akasha/Logos use their own job id as the key |
| Callbacks | **None** — callers poll. The worker never initiates connections to the NAS |
| URLs from callers | **None accepted.** Research requests carry a question, not URLs to fetch |

## Errors

All errors share one shape:

```json
{"error": {"code": "unavailable", "message": "Ollama is not responding", "retryable": true}}
```

| HTTP | `code` | Meaning | Caller mapping |
|---|---|---|---|
| 400 | `invalid_request` | Schema violation | Bug — raise |
| 401 | `unauthorized` | Missing/invalid token | Config error — raise |
| 404 | `not_found` | Unknown or expired job | Job lost — mark failed |
| 409 | `idempotency_conflict` | `Idempotency-Key` reused with a different body | Bug — raise |
| 409 | `not_awaiting_approval` | `POST /jobs/{id}/plan` only: the job is not waiting for its plan (cancelled, expired, already approved) | `ResearchConflict` — show the job as it is |
| 413 | `payload_too_large` | Request over size limit | Bug / split input |
| 429 | `queue_full` | Queue at `QUEUE_MAX`; `Retry-After` header set | `ResearchBusy` / retry later |
| 502 | `image_unavailable` | `POST /images` only: the image is gone, unreachable, too large or not an image | `ResearchImageUnavailable` |
| 503 | `unavailable` | A dependency is down (`message` says which) | `ResearchUnavailable` / `ReviewUnavailable` |

Network errors and timeouts are treated like `503`.

**Job failure codes** (in a failed job's `error`, same shape): `timeout` (job exceeded
its time limit), `unavailable` (a dependency died mid-job), `no_sources` (research
found nothing usable), `internal`, `plan_expired` (a research plan waited longer
than `PLAN_TTL_HOURS` for approval).

## `GET /v1/health`

Returns `200` whenever the worker process is up; `ok` reflects its dependencies.

```json
{
  "ok": true,
  "api_version": "1",
  "ollama":  {"status": "up", "models": {"review": "qwen3:30b", "research": "qwen3:30b"}, "loaded": []},
  "searxng": {"status": "up"},
  "gpu":     {"busy": false, "vram_used_mb": 812, "vram_total_mb": 24576},
  "queue":   {"queued": 0, "running": 0, "max": 20},
  "verifier": {"status": "up", "models": {"research": "bespoke-minicheck", "review": "gemma3:27b-it-qat"}}
}
```

- `ok` is `false` if Ollama or SearXNG is down (research needs both; review needs Ollama).
- `verifier` is the optional Mac: `up` \| `down` \| `not_configured`. It **does not
  affect `ok`** — jobs run without it unless they set `verify: "required"`.
- `ollama.loaded` lists models currently in VRAM — empty means the first job pays a
  ~10–30 s load.
- `gpu.busy` is `true` when another process (e.g. ComfyUI) holds most of the VRAM.

## `POST /v1/jobs`

Request:

```json
{
  "kind": "research",
  "request": { ... },
  "client": {"service": "akasha", "ref": "akasha-job-6f1c2e"}
}
```

`client.ref` is the caller's own job id (also sent as `Idempotency-Key`). No usernames
or other personal data.

Response `202` (or `200` for a repeated idempotency key):

```json
{"job": {"id": "j_01J9Z3K8", "kind": "research", "state": "queued",
         "created_at": "2026-10-11T09:12:03Z", "position": 1}}
```

## `GET /v1/jobs/{id}`

```json
{
  "job": {
    "id": "j_01J9Z3K8",
    "kind": "research",
    "state": "running",
    "progress": {"stage": "fetching", "message": "Reading 5 of 8 sources"},
    "created_at": "2026-10-11T09:12:03Z",
    "started_at": "2026-10-11T09:12:05Z",
    "finished_at": null,
    "expires_at": null,
    "result": null,
    "error": null
  }
}
```

| Field | Values |
|---|---|
| `state` | `queued` → `running` → `done` \| `failed` \| `cancelled`; research asked with `approve_plan` pauses in `awaiting_approval` after planning |
| `progress.stage` (research) | `loading_model`, `planning`, `searching`, `fetching`, `extracting`, `verifying`, `writing`, `second_check` |
| `progress.stage` (review) | `loading_model`, `reviewing`, `second_check` |
| `progress.stage` (discussion) | `loading_model`, `replying` |
| `result` | Set only when `state` is `done` (shapes below) |
| `error` | Set only when `state` is `failed` (same shape as API errors) |
| `expires_at` | When the result will be deleted (`finished_at` + `RESULT_TTL_HOURS`) |
| `plan` | Research with `approve_plan` only: `{queries: [{q, language}], approved, expires_at}`; otherwise `null` |

**Polling:** every 3–5 s while a user is watching; back off to 30 s otherwise. Import
promptly — results expire.

## `DELETE /v1/jobs/{id}`

Cancels a `queued`, `running` or `awaiting_approval` job; returns the job with
`state: "cancelled"`. Idempotent: cancelling a finished job returns it unchanged.

## `POST /v1/jobs/{id}/plan`

Approves the search plan of a job in `awaiting_approval`, as proposed or edited:

```json
{"queries": [{"q": "song dynasty tea whisking", "language": "en"}]}
```

At most 6 queries; `language` is a code like `en` or `zh-TW`. The job is queued
again, keeping its place ahead of jobs submitted after it, and runs from
searching. A job not awaiting approval answers `409 not_awaiting_approval`. To
reject a plan, cancel the job. An empty list is allowed: a refinement then
re-reads only its previous sources.

While a job waits, it holds no GPU and no place in the queue (it is not counted
against `QUEUE_MAX`). Its input stays stored until it finishes, like any queued
job. Unapproved after `PLAN_TTL_HOURS` (default 24), it fails as `plan_expired`.

---

## Research job (`kind: "research"`) — used by Akasha

**Request:**

```json
{
  "question": "Song-dynasty tea culture",
  "languages": ["en", "zh"],
  "max_sources": 8,
  "include_images": true,
  "known_articles": [
    {"ref": "song-dynasty/research/song-tea-bowls", "title": "Song tea bowls"}
  ],
  "verify": "auto",
  "approve_plan": false
}
```

| Field | Rules |
|---|---|
| `question` | Required, 3–500 chars. With `refine.feedback`, the **only** writer text used to build search queries |
| `languages` | Optional, default `["en"]` |
| `max_sources` | Optional, 1–15, default 8 |
| `include_images` | Optional, default `false` |
| `known_articles` | Optional, ≤ 200 entries, **refs and titles only — never bodies**. Lets the worker avoid duplicates and suggest links |
| `verify` | Optional second check on the Mac: `auto` (default — run if the verifier is up, else skip), `required` (fail with `unavailable` if it's down), `off` |
| `approve_plan` | Optional, default `false`. Stop after planning in `awaiting_approval` until `POST /jobs/{id}/plan` |
| `refine` | Optional: revise an earlier draft (below) |

**Refining.** `refine` turns a job into a revision of an earlier draft:

```json
"refine": {
  "feedback": "Focus on how ordinary people drank tea, not the court.",
  "previous": {"title": "Song-Dynasty Tea Culture",
               "facts": ["Tea was ground to powder and whisked into a froth."],
               "sources": [{"url": "https://…/song-tea", "title": "Tea in the Song Dynasty"}]},
  "exclude_urls": ["https://…/unreliable-blog"]
}
```

- `feedback` (1–2000 chars) goes to the planner, the fact extractor and the
  writer. Because it reaches the planner, it can end up in search queries, the
  same as the question.
- `previous.sources` that are not excluded are **fetched again first**, and every
  fact is re-extracted and its quote re-verified against the page. Nothing in
  `previous` is trusted as a fact; `previous.facts` only tell the planner what
  the last draft already found. New searches fill the rest of `max_sources`.
  When the kept sources already fill it, nothing is searched.
- `exclude_urls` are never read, whether they come from `previous` or from search.

The result has the same shape as any research result. Replacing the earlier
draft is the caller's decision.

**Result:**

```json
{
  "article": {
    "title": "Song-Dynasty Tea Culture",
    "body": "Tea in the Northern Song was ground to powder and whisked into a froth [[cite:s1]]. ...",
    "topic": "food",
    "era": "Northern Song",
    "facts": [
      {"text": "Tea was ground to powder and whisked into a froth.",
       "citations": [{"source": "s1", "quote": "the powdered tea was whisked in the bowl until a white froth formed"}],
       "check": {"status": "supported"}}
    ],
    "links": ["song-dynasty/research/song-tea-bowls"],
    "image_candidates": [
      {"url": "https://…/tea-bowl.jpg", "source": "s3", "caption": "Jian ware tea bowl, Song dynasty",
       "license": "CC0 (Met Open Access)"}
    ]
  },
  "sources": [
    {"key": "s1", "url": "https://…", "title": "…", "site": "…", "language": "en",
     "retrieved_at": "2026-10-11T09:13:40Z",
     "excerpts": ["the powdered tea was whisked in the bowl until a white froth formed"]}
  ],
  "dropped_facts": [
    {"text": "…", "reason": "quote_not_found"},
    {"text": "Tea bowls were always glazed white.", "reason": "unsupported"}
  ],
  "verification": {"status": "checked", "model": "bespoke-minicheck", "reason": null,
                   "checked": 2, "removed": 1},
  "model": "qwen3:30b",
  "generated_at": "2026-10-11T09:16:22Z"
}
```

| Rule | Detail |
|---|---|
| Citations | Every fact cites ≥ 1 source with a quote; the worker **verified each quote appears verbatim** in the fetched page text |
| Second check | When the verifier runs, each fact's quotes are checked for **actual support** of the fact: `check.status` is `supported` or `partial`; unsupported facts move to `dropped_facts` with reason `unsupported`. When skipped or off, every fact is `unchecked` |
| `verification` | `status`: `checked` \| `skipped` (verifier unavailable) \| `off`; plus the verifier model, the reason, and how many facts were checked and removed. **Akasha should show this in the inbox** so the writer knows whether a draft was second-checked |
| `dropped_facts` | Facts that failed either check — shown to the writer for transparency, never imported as facts. Reasons: `quote_not_found`, `no_citation`, `source_unreachable` (first pass), `unsupported` (second check) |
| Source keys | `s1`, `s2`… are local to the result. **Akasha assigns slugs** during import (deduplicating by normalized URL) and rewrites `[[cite:s1]]` tokens to `[[sources/<slug>]]` |
| `links` | Only refs from `known_articles` |
| Nested data | The API is nested; **flattening into Akasha's flat documents is the import module's job** |
| Images | Candidates only — URL, source, caption, license. Importing is the writer's action |

**Limits:** request ≤ 64 KB; job time limit 15 min (→ `failed`, code `timeout`).

---

## Review job (`kind: "review"`) — used by Logos

**Request:**

```json
{
  "chapter": {
    "title": "Chapter 7 — The Tea House",
    "blocks": [
      {"id": "b1", "text": "Lin Qingyu lifted the teapot and poured…"},
      {"id": "b2", "text": "…"}
    ]
  },
  "references": [
    {"ref": "ember-pact/characters/lin-qingyu", "kind": "canon",     "title": "Lin Qingyu", "text": "…"},
    {"ref": "song-dynasty/research/song-tea",   "kind": "research",  "title": "Song tea",   "text": "…"},
    {"ref": "ember-pact/deviations/qi-lanterns","kind": "deviation", "title": "Qi lanterns","text": "…"},
    {"ref": "song-dynasty/research/watchlist",  "kind": "watchlist", "title": "Anachronism watchlist", "text": "…"}
  ],
  "dialect": "en-GB",
  "checks": ["continuity", "anachronism", "prose"],
  "verify": "auto"
}
```

| Field | Rules |
|---|---|
| `chapter.blocks` | Plain text per block, with stable ids so findings anchor to the manuscript |
| `references` | Assembled by Logos ([`docs/logos/llm-review.md`](../logos/llm-review.md)): the book world's deviations and watchlist first, then the articles the chapter mentions, with **only `verified` research**; at most 40, each cut to 1,500 characters. `kind`: `canon` \| `research` \| `deviation` \| `watchlist` |
| `checks` | Any of `continuity` (vs. canon), `anachronism` (vs. research + watchlist), `prose` |
| `dialect` | Passed through, as for the rule-based advisor |
| `verify` | Same as for research: `auto` (default), `required`, `off` |

**Result:**

```json
{
  "issues": [
    {"check": "anachronism", "severity": "warning", "confidence": "likely",
     "block": "b1", "quote": "lifted the teapot and poured",
     "message": "Song-dynasty tea was powdered and whisked in bowls; steeping in teapots is a Ming-era habit.",
     "suggestion": "Show her whisking powdered tea in a bowl.",
     "reference": "song-dynasty/research/song-tea",
     "verified": true}
  ],
  "verification": {"status": "checked", "model": "gemma3:27b-it-qat", "reason": null,
                   "checked": 3, "removed": 2},
  "model": "qwen3:30b",
  "generated_at": "2026-10-11T09:20:51Z"
}
```

| Rule | Detail |
|---|---|
| `quote` | Must appear verbatim in the cited block — the worker drops issues whose quote it can't find |
| Second check | When the verifier runs, each issue is re-judged against its block and reference: confirmed issues get `verified: true`; issues judged not real are **removed** (counted in `verification.removed`). When skipped or off, `verified` is `null` |
| `verification` | Same shape as for research. Logos can show "second-checked" vs. "first pass only" in its review panel |
| `reference` | The `ref` the issue is based on; `null` for `prose` issues |
| Deviations | Issues contradicting a `deviation` reference are suppressed by the worker |
| `severity` / `confidence` | `info` \| `warning`; `possible` \| `likely` |
| Mapping | Logos maps issues onto the finding shape its `RuleBasedWritingAdvisor` already produces |

**Limits:** request ≤ 1 MB; job time limit 5 min.

---

## Discussion job (`kind: "discussion"`) — used by Logos

A writer answering one issue from a review -- "that's deliberate", "why?",
"what would you do instead?" -- and the editor's reply. **Logos keeps the
conversation** and sends all of it every turn; the worker keeps nothing between
jobs, as for every kind. It runs on `REVIEW_MODEL`: the editor who raised an
issue answers for it.

**Request:**

```json
{
  "issue": {"check": "anachronism", "quote": "lifted the teapot and poured",
            "message": "Song-dynasty tea was powdered and whisked in bowls; steeping in teapots is a Ming-era habit.",
            "suggestion": "Show her whisking powdered tea in a bowl."},
  "passage": "Lin Qingyu lifted the teapot and poured.",
  "reference": {"ref": "song-dynasty/research/song-tea", "kind": "research",
                "title": "Song tea", "text": "…"},
  "messages": [
    {"role": "writer", "text": "The teapot holds hot water for the whisking, not tea. Is that wrong too?"}
  ],
  "dialect": "en-GB"
}
```

| Field | Rules |
|---|---|
| `issue` | The issue as the review reported it: `check`, `quote`, `message`, and `suggestion` (or `null`) |
| `passage` | The issue's block **as it reads now**, up to 20,000 characters. It may have been revised since the review |
| `reference` | The article the issue cites, shaped as in a review request; `null` for a prose issue or one whose article the writer can no longer read |
| `messages` | The conversation so far, oldest first: 1–40 of `{role: "writer" \| "editor", text}`, each at most 4,000 characters |
| `dialect` | As for a review |

**Result:**

```json
{
  "reply": "A kettle of hot water is right for the period -- whisked tea needs it. It's the pouring into cups that reads as steeped tea.",
  "stance": "revises",
  "suggestion": "lifted the kettle and poured hot water over the powdered tea in her bowl",
  "model": "qwen3:30b",
  "generated_at": "2026-10-11T09:25:09Z"
}
```

| Rule | Detail |
|---|---|
| `stance` | Where the editor now stands: `maintains` (the issue holds), `revises` (it holds, but a different fix would serve better), `withdraws` (the writer has shown it is wrong, or deliberate). The writer still decides the issue's status |
| `suggestion` | A new minimal fix, only with `revises`; otherwise `null` |
| `reply` | At most 2,000 characters. An empty one fails the job (`internal`) |
| No second check | A reply is conversation, not a finding: the verifier is not asked |

**Limits:** request ≤ 256 KB; job time limit 2 min.

---

## Images (`POST /v1/images`) — used by Akasha's research inbox

A research result names images only as candidates. Each carries a
**`fetch_token`**: an HMAC of its URL under a key that never leaves the box.

```json
{"url": "https://example.org/tea-bowl.jpg", "source": "s3",
 "caption": "Jian ware tea bowl, Song dynasty", "license": "CC0 (Met Open Access)",
 "fetch_token": "3q2-7wEXAMPLEtokenSignedByTheWorker_abcdefg"}
```

To show or import one, the caller posts it back:

```json
POST /v1/images
{"url": "https://example.org/tea-bowl.jpg",
 "token": "3q2-7wEXAMPLEtokenSignedByTheWorker_abcdefg",
 "size": "preview"}
```

The answer is the image's bytes, with `Content-Type` saying which format (JPEG,
PNG or WebP -- exactly what Akasha stores), not JSON.

| Rule | Detail |
|---|---|
| Only its own URLs | A URL is fetched only with the token the worker issued for it. A caller -- even a compromised NAS -- can never make the box fetch an address of its choosing |
| Tokens last | They don't expire with the job, so a draft can import its images days later. Rotating the key (`WORKER_SIGNING_KEY`, or deleting the key file in the data volume) revokes all of them |
| `size` | `preview`: at most 360 px, re-encoded (JPEG, or PNG when transparent), for showing candidates. `full` (default): the original bytes, for importing |
| Guarded fetching | Same fetcher as research: public addresses only (re-checked after every redirect), ports 80/443, the image cap (`IMAGE_MAX_BYTES`, 20 MB), and it must open as an image |
| Nothing kept | The worker stores neither the image nor the URL; its log records only the size requested and the bytes returned |
| Errors | `400 invalid_request` (malformed, or the token doesn't match), `502 image_unavailable` (gone, unreachable, too large, not an image, refused address) |

