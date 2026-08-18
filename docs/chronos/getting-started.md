# Getting started: build The Ember Pact

A walkthrough for a writer with no terminal. You will build the demo story by
hand — a small cast, six scenes, five threads — then **break it on purpose** and
watch Chronos report all three of its continuity checks at once. About twenty
minutes.

`docker/seed_demo.py` builds the same book in a few seconds. Do that if you only
want something to look at. Do *this* if you want to know where the story rules
come from, because you meet each one at the moment it fires.

> **If the demo is already seeded**, the ids below are taken. Either use your own
> (any name works — only the ids in your own links change), or delete the seeded
> book first: **✎** beside its title → **Delete book**.

**What you will end up with**

| | |
| --- | --- |
| A world | 3 characters, 1 item, 3 places, in Articles |
| A calendar | "Imperial Reckoning" in the library — hours, days, months, years |
| A book | "The Ember Pact", counting in that calendar |
| Six scenes | five sound, one a disputed sighting |
| Five threads | three sharing one ending, one contesting it, one broken |
| Three findings | a temporal conflict, an ordering violation, a thread that never arrives |

---

## Before you start

The stack is up (`docker compose -f docker/docker-compose.nas.yml up --build -d`)
and **http://localhost:5002/** answers.

**Register.** The first account becomes the administrator. Everything below is
done as that one user; nothing here needs a second account or an admin console.

Two services share that login: **Articles** (Akasha) holds *what exists* in your
world, **Timeline** (Chronos) holds *what happens*. The switcher is top right.

---

## 1. Write the canon

Chronos never invents a character or a place — it *references* them, and refuses
a reference to something that is not there. So the cast comes first.

In **Articles**, click **New article**. The first one asks for four things:

| Field | Value |
| --- | --- |
| World | `ember-pact` |
| Category | `characters` |
| Title | `Sir Aldric` |
| Slug (id) | `aldric` |

The world and the category do not need to exist first — creating the article
creates them, and you immediately own what you made. Write a line or two of body
text and save.

Repeat for the rest. Only the title and slug matter for this guide; the bodies
are yours to enjoy.

| Category | Title | Slug |
| --- | --- | --- |
| `characters` | Sir Aldric | `aldric` |
| `characters` | Lyra Vane | `lyra` |
| `characters` | Magister Corwin | `corwin` |
| `items` | The Ember Seal | `ember-seal` |
| `locations` | Highkeep | `highkeep` |
| `locations` | Emberport | `emberport` |
| `locations` | The Throne Hall | `throne-hall` |

> **Why the slug matters.** It is the article's permanent address, and it is what
> a scene stores. Titles can be changed freely afterwards; slugs cannot.

---

## 2. Build a calendar

Switch to **Timeline**, and before the book: **Calendars** on the shelf.

Calendars live in a library of their own, not inside a book. A book *chooses*
one — that is the only way it can get a calendar, and the API refuses a book
that tries to describe its own. It sounds like a detour and it pays for itself
immediately: the next book you write picks this calendar in a click, and a
calendar you share travels to the people you write with.

**+ New calendar**, then the preset **Hours, days, months, years** — a base unit
of `hour` with cycles of 24, 30 and 12. Name it `Imperial Reckoning` and set the
era label to `AF`.

The form reads your choice back in plain language as you build it:

> *Ticks are hours: 24 hours to a day, 30 days to a month, 12 months to a year.*

That sentence is the whole point of the calendar. A scene is always *stored* at a
whole number — a **tick** — and the calendar decides how that number reads, and
lets you type a date instead of it:

| Tick | Reads as |
| --- | --- |
| `0` | Year 1, Month 1, Day 1, 00:00 AF |
| `24` | Year 1, Month 1, Day 2, 00:00 AF |
| `48` | Year 1, Month 1, Day 3, 00:00 AF |
| `200` | Year 1, Month 1, Day 9, 08:00 AF |

The translation runs both ways, so when you write a scene in step 4 you can give
it a date and Chronos works out the tick. Ticks remain the stored truth — every
continuity check runs on them, which is why changing calendars never moves a
scene.

---

## 3. Create the book, and attach the calendar

*Your books* offers **+ New book**.

| Field | Value |
| --- | --- |
| Title | `The Ember Pact` |
| Id | `ember-pact` (derived from the title — leave it) |
| Overview | *Four threads converge on a coronation nobody wants.* |
| World | `ember-pact` |

Then **Time**. Under **How it counts**, choose **From your library** and pick
**Imperial Reckoning**. (If you skipped the last section, **＋ New calendar**
here builds one without leaving the form — into the library, because that is
where calendars live either way.) Leave it on **No calendar** and scenes read
back as bare integers, which is a real choice and not a missing one.

**Create book**, and you land on its (empty) plotline table.

> **The book takes a copy.** Editing *Imperial Reckoning* in the library later
> will not re-date this story. The book notices and offers you the change —
> *"mara/imperial has changed since this book copied it"* — with the new reading
> shown before you accept. Nothing moves until you click. Note that accepting is
> one-way: library calendars keep no history, so there is no going back to the
> revision you had.

> **Changing your mind.** **✎** beside the book's title reopens this form to
> rename it, edit the overview, or point it at a different calendar. Swapping is
> safe by construction: ticks are the stored truth and a calendar only formats
> them, so a new calendar re-labels every scene without moving one.

> **More than one at a time.** **+ Add another calendar** attaches a second
> reckoning over the same scenes — a rival culture's count — and a switcher
> appears above the book to read through either. Give the second one a span
> (*kept from tick … until …*) and it will decline to date scenes outside it,
> reading *before the Elvish Count* rather than inventing a year nobody counted.
> That is how a calendar belonging to a destroyed culture behaves correctly
> without any special case: it simply stops.

---

## 4. Write the scenes

Click **Scenes** in the book header. This is the scene library: every scene in
the book, filtered and paged, and where you write, read and remove them.

**+ New scene**, five times. The **Place**, **Characters** and **Items** fields
search the articles you just wrote — pick from the list rather than typing.

| Title | Id | Place | Starts | Ends | Characters | Items |
| --- | --- | --- | --- | --- | --- | --- |
| Aldric Departs | `aldric-departs` | Highkeep | `0` | `24` | Aldric | — |
| Lyra Infiltrates | `lyra-infiltrates` | Emberport | `0` | `48` | Lyra | — |
| The Harbor Exchange | `meet-at-emberport` | Emberport | `48` | `72` | Aldric, Lyra | The Ember Seal |
| Corwin Plots | `corwin-plots` | Highkeep | `96` | `120` | Corwin | — |
| The Coronation | `the-coronation` | The Throne Hall | `200` | `210` | Aldric, Lyra, Corwin | The Ember Seal |

**Date or Tick.** Because this book has a calendar, the timing fields start in
**Date** mode: a box per unit — Year, Month, Day, Hour — rather than one raw
number. Type *Year 1, Month 1, Day 1* and the line beneath tells you what it
became: *"Year 1, Month 1, Day 1, 00:00 AF → Year 1, Month 1, Day 2, 00:00 AF
(24 hours) — ticks 0 → 24."* Switch to **Tick** to type the number directly; the
same line translates the other way. Either mode saves the same scene — the
table above lists ticks because they are what gets stored.

> **You can stop early.** Fill in Year, Month and Day and leave Hour blank and
> the date means *the whole of that day*. Put the same date in both fields and
> the scene covers exactly that day and nothing more, which is usually what you
> meant. Fill in the hour too when you need the scene to be more precise than
> that.

> **Leave the timing blank** if you do not know when a scene happens yet. An
> unscheduled scene is a to-do, not an error: it takes part in no timing rule
> until you place it, and the library marks it `unscheduled`.

> **Dates that do not exist are refused.** Day 31 of a 30-day month, or a date
> in a reckoning that had not begun yet, comes back as an error rather than
> being quietly rounded to something you did not ask for.

Back in the library, try **⤢** on a row. The whole scene opens beside the table —
its description, and its place, cast and items as chips. Click **Highkeep** and
the article you wrote in step 1 opens on top of it. That is the canon and the
timeline joined up: one set of facts, referenced from both sides.

---

## 5. Thread the plotlines

A **plotline** is an ordered list of scenes plus the goals it serves. Order is
the contract — it is what Chronos checks against the clock.

Goals are records of their own, so write them before the threads that point at
them. **Goals** in the book's header, then **+ New goal**, three times:

| Name | Rests on | Achieved at |
| --- | --- | --- |
| Deliver the Ember Seal | — | The Harbor Exchange |
| Expose the traitor | — | The Harbor Exchange |
| See the Seal pressed to the charter | *both of the above* | The Coronation |

The diagram draws the third one below the two it rests on, and calls all three
`achieved` — the harbour scene ends at hour 72 and the coronation begins at 200,
so nothing is delivered before what it was resting on. (You can skip **Achieved
at** while drafting; a goal with no scene yet is a note, not a fault.)

Three of these threads end the same way, at the coronation. Rather than repeat
that ending in each, you will write it **once** in a trunk and have the others
*continue into* it. So build the trunk first.

### The trunk

Back on the plotline table, **+ New plotline**:

- **Name** `The Road to the Crown` (id `the-road-to-the-crown`)
- **Goals** — search for `See the Seal pressed to the charter` and pick it
  (**+ New goal** here writes one without leaving the editor)
- **Add scene** → *An existing scene* → `The Harbor Exchange`, then
  `The Coronation`

**Create plotline.**

### The ending

Reopen it and click **✦** on *The Coronation*: *"Make this the book's ending."*

The **terminus** is the one scene every thread in the book is expected to reach.
Until you name one, the third story rule has nothing to check and stays quiet.
It is a book-level fact, so it saves immediately rather than waiting for the
editor's Save.

### The three that join it

Two threads continue into the trunk. For each: **+ New plotline**, add its own
scene, then set **Continues into** → *The Road to the Crown*.

| Name | Its own scene | Goal | Continues into |
| --- | --- | --- | --- |
| The Knight's Road | Aldric Departs | Deliver the Ember Seal | The Road to the Crown |
| The Spy's Shadow | Lyra Infiltrates | Expose the traitor | The Road to the Crown |
| The Magister's Gambit | Corwin Plots, The Coronation | *(none yet)* | — *(none)* |

The magister joins only at the very end, so he keeps his own full path rather
than continuing into the trunk.

Open *The Knight's Road* now. It lists three scenes: its own, then two shown
locked with a 🔒 and marked *from the-road-to-the-crown*. Those are inherited —
stored on the trunk, so an edit has to go there. Add a scene to the trunk and
both threads get it.

**Four threads, all green.** The book's status pill reads `consistent`.

---

## 6. Break it on purpose

A witness claims to have seen Aldric at the harbour. They are mistaken, and the
mistake is the kind that hides in a manuscript for months.

**Scenes → + New scene:**

| Title | Id | Place | Starts | Ends | Characters |
| --- | --- | --- | --- | --- | --- |
| Aldric Seen At Emberport | `aldric-at-emberport` | Emberport | `10` | `30` | Aldric |

Then **+ New plotline**, named `The Witness's Tale`, with no goal for now
(the report will note it, which is the point — a thread without a purpose yet is
a draft, not a mistake), and two scenes added **in this order**:

1. The Harbor Exchange
2. Aldric Seen At Emberport

You will see the verdict change **before you save it**. Every reorder is sent to
a preview endpoint that runs the candidate through the same rules a save would,
so the marks appear as you drag. Save anyway — findings never block a write.

---

## 7. Read what it is telling you

The book now reads `conflicted`, and the three checks are all firing. Open *The
Witness's Tale* — a banner counts the problems and links to the scenes carrying
them, and each finding sits under the scene it is about.

### 1. A temporal conflict

On *Aldric Seen At Emberport*:

> **!** 'Sir Aldric' cannot be here and in 'Aldric Departs' at once — that scene
> is at 'Highkeep' over an overlapping time.  **show**

Aldric rides out at hour 0 and arrives at hour 24; the sighting puts him on the
quay from hour 10. **Same character, two places, overlapping times.**

This is a fact about the scenes themselves, not about this thread, so it is
reported wherever either scene appears — open *The Knight's Road* and you will
find the mirror of it on *Aldric Departs*. The **show** button jumps to the other
scene, which is usually where the fix belongs.

Notice that the message names *Sir Aldric* and *Highkeep*, not `aldric` and
`highkeep`. The rules module cannot see Akasha, so it quotes slugs; the browser
swaps in the titles it is allowed to read. Someone without the grant keeps the
slug, which is the honest outcome.

### 2. An ordering violation

Reported on both ends of the pair. On *Aldric Seen At Emberport*:

> **!** 'The Harbor Exchange' has not ended when this scene begins.

and on *The Harbor Exchange*:

> **!** This scene has not ended when 'Aldric Seen At Emberport' begins.

You listed the exchange (hours 48–72) *before* the sighting (hours 10–30). A
plotline's order is a claim about sequence, and the clock disagrees.

### 3. A thread that never arrives

Under the thread as a whole, rather than on any one scene:

> **i** Plotline does not end at the book's terminus. It ends at 'Aldric Seen At
> Emberport'.

Every thread is expected to reach the coronation. This one stops at the quay.
Note this check only speaks once a terminus exists — before you set one in step
4, every thread in the book would have carried the same complaint, which would
have said nothing at all.

> **Nothing was blocked.** All three writes succeeded. Chronos records what you
> tell it and reports what does not add up — a draft is allowed to be wrong, and
> the report is a to-do list rather than a gate.

### All three at once

You found those by opening one thread and knowing where to look. **Report**, in
the book's header — or the `conflicted` pill on the book's card, which is a link
— lists all of them on one page, grouped by kind, each naming the scene it is
about and every thread it shows up on. The temporal conflict appears **once**
there, not twice: it is one problem seen from two threads, and the report says
so. Clicking a scene takes you to it, on its thread, scrolled to and flashed.

---

## 8. Fix all three

**The conflict.** In the library, **✎** on *Aldric Seen At Emberport* and change
its timing to **30 → 40**. He is off the road by hour 24, so the sighting is now
merely late, not impossible. Watch the finding vanish from both threads.

**The order and the ending, together.** Open *The Witness's Tale*:

1. Remove *The Harbor Exchange* with **✕** — it is about to arrive from the trunk
   instead.
2. Set **Continues into** → *The Road to the Crown*.
3. **Save changes.**

Its resolved path is now the sighting (30–40), then the exchange (48–72), then
the coronation (200–210): in order, and ending where every other thread ends.

The book's pill turns **`consistent`**.

> Two other ways to have fixed the order, both worth knowing: drag a scene by its
> **⠿** handle, or focus a row and press ↑/↓; and **Sort by time**, which puts
> the dated scenes in chronological order in one click.

---

## 9. Tidy up

Housekeeping is part of writing, and all of it is here.

- **A scene you no longer want** — **✕** in the library. If a thread still uses
  it you are told which, and offered to remove it from them first. The book's
  ending refuses to be deleted until you designate another.
- **A thread** — **Delete plotline** in its editor. The scenes stay in the book;
  only the thread through them goes.
- **The whole experiment** — **✎** beside the book's title → **Delete book**. It
  tells you exactly what goes with it, and asks you to type the book's id.
  Your articles in Akasha are untouched: they belong to the world, not the book.

---

## What to try next

- **Add a scene to the trunk** and watch it appear on all three threads at once.
- **Insert one into the middle** of a thread with **↥** / **↧** on a row, instead
  of appending and dragging.
- **Story Map** from the book page — tick a few threads and watch the merge and
  the split get drawn. Click a scene to open it in place; unfold a "N scenes"
  band to see the stretch a thread walks alone.
- **Leave a scene unscheduled** and see the window its neighbours imply: the
  earliest and latest it could possibly go.
- **Swap the calendar** to *No calendar* and back, and confirm no verdict moves.
- **Attach a second reckoning** with an end tick, and read the same scenes
  through it — the scenes past its end decline to be dated rather than
  inventing a year.
- **Edit the calendar in the library** and come back to the book: it will
  offer you the change rather than having taken it.

## Where to read further

- [README](README.md) — the model, the API, and every rule in one page
- [Plain-language overview](OVERVIEW.md) — what this is for, without the schema
- [Design](design.md) — why the rules are shaped the way they are
- [What the UI cannot do yet](ui-api-gaps.md) — the honest list
