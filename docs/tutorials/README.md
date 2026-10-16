# Tutorials

The **Tutorials** tab: short, illustrated lessons that take a new writer from
their first Akasha article to a first draft of their manuscript. They're
ordinary pages, not an overlay on the app, and **public**, so anyone can read
how it works before they have an account. The login page links to them as
"New here? See how it works."

- `/tutorials/` is the hub: the course, its parts, one card per lesson.
- `/tutorials/<lesson>` is a lesson: three to five steps, each one action with
  one picture, and "What you made" at the end.
- `/tutorials/glossary` is the words the lessons use, each in a sentence or two.

## The course

Fourteen lessons and an unnumbered start, about 47 minutes in all. One story
grows through them: the world *Lantern Coast*, its lighthouse keeper Ysolde
Marr, the book *The Last Lamp*.

| | Lessons |
| --- | --- |
| Before you start | make an account, sign in, find your way around |
| Part 1 · Your world (Articles) | A home for your story · Your first article · Places and people |
| Part 2 · Your story's shape (Timeline, Maps) | Start a book · Your first scene · Threads through the story · Consistent, or conflicted · Draw the world *(optional, with a sample map to download)* |
| Part 3 · Your draft (Manuscripts) | Start writing · The writing page · Your world beside you · Chapter after chapter · Read it back · A first draft |

Two lessons teach what walking the app showed. A `[[name]]` link looks only
in its own category, so "Places and people" links with the editor's
`🔗 Insert link`. A book followed exactly comes out CONFLICTED (no ending is
marked), so "Consistent, or conflicted" reads the Report and marks the
ending with ✦.

## How a lesson is written

Each lesson is a TOML file in `src/visualizer/tutorials/lessons/`.
`course.toml` names them in reading order. It has an unnumbered *prelude*
("Before you start"), then parts whose lessons are numbered.
`glossary.toml` defines the words.

```toml
title = "Your first article"
summary = "Write a page for your main character."        # the hub card's line
lede = "An {article} is one page about one thing in your story."
needs = "a-home-for-your-story"                           # an earlier lesson

[[steps]]
title = "Give it a name"
text = "Type your character's name into **Title**, then press `Continue`."
shot = "your-first-article/name-it"
alt = "The New article dialog, with Ysolde Marr typed as the title"
note = { kind = "good-to-know", text = "The {slug} fills itself in." }

[made]
text = "Your first article."
shot = "your-first-article/made"
alt = "The finished article for Ysolde Marr"
```

A step's text may be one string or a list of paragraphs. A note is a `tip`,
`good-to-know` or `if` ("If something looks different"). A lesson can also set
`optional = true`, a `cover` picture for its card, and `downloads` (files in
`static/downloads/`).

Text is escaped, and then three marks are drawn. Nothing else can reach the page.

| Write | Shows as |
| --- | --- |
| `` `＋ New article` `` | a key cap of the control on screen |
| `**Title**` | bold |
| `{world}` or `{worlds\|world}` | a link to the glossary entry |

### The rules, and what keeps them

`validate.py` lists every broken rule and
`tests/tutorials/test_catalog.py` asserts the list is empty:

- **one to five steps**, each **three sentences at most** (split a longer one);
- every picture a lesson shows has been taken, and has **alt text**;
- every picture taken is shown by some lesson;
- every **label quoted in backticks was on screen** in that lesson's own
  pictures. This is checked against what the camera saw, not against the
  source, where labels are assembled ("＋ New " + the word for an article);
- a lesson only `needs` one read before it;
- every `{word}` has a glossary entry;
- every offered download exists.

## The pictures

Every picture is taken by a camera that walks the real UI as a brand-new
writer, *wren*, on an empty stack. A lesson's pictures carry on from the
previous lesson's, so they show what someone following along will see. Each is
taken **at two widths** (1280px and 390px) **and in both themes**. The page
picks the width with `<picture>` and the theme from `data-theme`, and draws
the rings that point at what to press. They're WebP files in
`src/visualizer/tutorials/static/shots/`, with `shots.json` recording each
one's size, rings and the labels on screen. They're committed, about 12 KB
each.

```sh
docker compose -f docker/docker-compose.screenshots.yml run --rm --build tutorial-shots
```

The camera runs in the screenshot job's image: no network, an in-memory
database, and two writable folders, the pictures and a debug folder. It
creates an administrator first, so wren is an ordinary account like most
readers'. A picture nobody takes any more is deleted. If a recipe can't find
what its lesson tells a writer to press, the run **fails** and leaves the old
pictures in place, with a screenshot of the moment in
`screenshots/tutorial-debug/`. That means the lesson has gone stale.

- `docker/tutorial_recipes.py` has one function per lesson, in reading order.
- `docker/tutorial_camera.py` has `Camera` (both widths, both themes, the
  crop, the rings, the labels seen, handed to a store it's given) and `Ui`,
  which does what a lesson describes by the labels a writer sees. Frames say
  what to crop: `element`, `around(*targets, within=dialog)` (a clean,
  full-width slice of a dialog), `window_top` and `window`, and `per_size`
  for a different crop on a phone. `shoot(..., prepare=)` re-creates a state
  at each width, for a popup placed where it opened or a phone drawer.
- `docker/tutorial_shots.py` is the entry point: the dev server, the
  administrator, the recipes, and the WebP files and manifest.

To iterate on a recipe without rebuilding, run the image with this
checkout's `src/` and `docker/` mounted read-only and the pictures going to a
scratch folder: mount `src` at `/app/src`, `docker` at `/app/docker`, a
scratch folder at `/out` and another at `/debug`, then run
`python /app/docker/tutorial_shots.py` in `visualizer-shots-tutorial-shots`
with `--network none --shm-size 1g`.

### Adding a lesson

1. Write `lessons/<slug>.toml` and name it in `course.toml`.
2. Add its recipe to `docker/tutorial_recipes.py` and to `RECIPES`, in the same
   place.
3. Run the camera, then `pytest tests/tutorials`. A problem names the lesson
   and the rule it breaks.

## How it's built

A fifth small app, mounted by `stack.py` at `/tutorials` exactly as Prithvi is
at `/prithvi`. It has no database of its own. Everything it uses is handed to
`create_app`: a `LessonCatalog`, a `ShotLibrary`, the accounts store and the
`ServiceLinks`. Nothing in the package opens a file or reads the environment on
its own, and `stack.py` picks the real implementations.

| Module | Holds |
| --- | --- |
| `lessons.py` | the values (`Course`, `Lesson`, `Step`, …) and the parser, which names the file and place of any mistake |
| `catalog.py` | `LessonCatalog`; `load_catalog(directory, read)` reads the course once |
| `shots.py` | `ShotLibrary`, the manifest's shape on both sides, the ring arithmetic |
| `inline.py` | the three marks, and the counts the rules need |
| `views.py` | pure functions from catalog and pictures to what a page shows |
| `validate.py` | the rules above |
| `routes.py` | three thin views; every page lights the tab (`is_home`) |
| `app.py` | wiring only |

In the shared navigation, Tutorials is the fifth tab. On a rail it sits under
a hairline, since it's *about* the four workspaces. On a phone each tab has an
equal share but is never narrower than its own label, so five fit a 320px
screen. The glyphs, a signpost included, are drawn once in
`auth/templates/_service_glyph.html` for the nav and the hub.

## Decisions

Taken on 2026-10-16:

- **Public.** The pages hold no one's data.
- **Not interactive.** Full pages to read beside the app, not an overlay
  inside it. The earlier interactive guide is shelved.
- **Named `tutorials`.** It's a guide to the services rather than one of them,
  so it has no Sanskrit or Greek name.
- **Both themes photographed**, because light pictures glare on a dark page.
- **Pictures committed**, so the NAS serves them with no browser and no build
  step.
