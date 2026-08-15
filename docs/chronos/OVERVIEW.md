# Chronos, in plain language

**Chronos is a continuity assistant for people who write fiction.**

You tell it what happens in your story — who was there, where, and when. It
keeps track, and it tells you when the story contradicts itself: a character in
two places at once, scenes that happen in an impossible order, a storyline that
never rejoins the ending.

It does not write anything for you, and it never changes your words. Think of it
as a very patient continuity editor who has memorised every scene and never gets
tired of checking.

> **Who this is for:** anyone curious what Chronos does. No technical knowledge
> assumed. At the moment Chronos is a service other programs talk to — there is
> no point-and-click screen for it yet — but the ideas below are the whole of
> it, and they're what any future screen will show.

---

## The four ideas

Everything in Chronos is built from four things. That's the entire vocabulary.

### 1. An Event — one scene

An **Event** is a single moment of your story:

> **The Harbor Exchange.** Aldric and Lyra, carrying the Ember Seal, at
> Emberport, from the morning of Day 3 to the morning of Day 4.
>
> *"Aldric and Lyra exchange the Ember Seal beneath the harbour market awnings."*

So an event records **who** was there, **what** they had with them, **where**
they were, **when** it started and ended, and **what happened** — as much prose
as you like.

### 2. A Plotline — one thread, in order

A **Plotline** is a sequence of events that form one thread of your story, plus
the **goals** that thread is chasing.

> **The Knight's Road** — *Goals: deliver the Ember Seal; reach the coronation
> alive.*
> 1. Aldric Departs
> 2. The Harbor Exchange
> 3. The Coronation

The order matters, and it is a promise: each scene must finish before the next
one starts. If you list them in an impossible order, Chronos notices.

### 3. A Book — all the threads together

A **Book** holds all the plotlines of one story. A book might have the knight's
journey, the spy's infiltration, and the schemer's plotting all running at once.

### 4. The Terminus — where everything lands

Every book has one ending that all its threads must reach: the **Terminus**.

> Every plotline in *The Ember Pact* ends at **The Coronation**.

This is the one structural rule Chronos asks of a finished book. Threads can
wander wherever they like — but they all have to arrive.

---

## Threads that share scenes

Here's where it gets useful. **Two plotlines can contain the same event.** When
they do, you get the two shapes every multi-threaded story is made of:

```
  Aldric Departs ─┐
                  ├─► The Harbor Exchange ─┐
Lyra Infiltrates ─┘                        │
                                           ├─► The Coronation
                        Corwin Plots ──────┘
```

- **Convergence** — threads coming *together* at a scene. Aldric's road and
  Lyra's shadow both run through The Harbor Exchange: that's where they meet.
- **Divergence** — a scene that threads split *out of*. One event, two different
  continuations.

Because the shared scene is one single event, not two copies, editing it updates
every thread that uses it. There's no such thing as two versions of the same
scene drifting apart.

### Sharing a whole ending

Once threads have merged, they usually run together to the finish — and listing
those closing scenes over and over in every thread gets tedious fast. Worse, if
you later slip a new scene into the ending, you'd have to remember to add it to
*every* thread, and any you miss quietly falls out of step.

So a thread can simply say **"from here I continue into that one."**

> **The Trunk** — The Harbor Exchange → The Coronation
> **The Knight's Road** — Aldric Departs, *then continues into The Trunk*
> **The Spy's Shadow** — Lyra Infiltrates, *then continues into The Trunk*

The ending is written once. Add a scene to The Trunk and both threads get it
immediately. Chronos still reads each thread as its complete journey — Aldric
Departs → The Harbor Exchange → The Coronation — so all the usual checks apply,
including whether the handover point makes sense in time.

The only thing it won't let you do is make the chain circular — A continuing
into B continuing back into A. There's no story that describes, so it refuses
rather than reports.

You can ask Chronos about any scene — *"which threads meet here, and where did
they each come from?"* — and it will tell you in words:

> **The Harbor Exchange** — convergence *(Year 1, Month 1, Day 3, Emberport)*
> - ← The Knight's Road, arriving from "Aldric Departs" *(Day 1)*
> - ← The Spy's Shadow, arriving from "Lyra Infiltrates" *(Days 1–3)*
> - → both continue together to "The Coronation" *(Day 9)*

---

## How time works

Chronos counts time in plain numbers, starting from zero. Think of it as
"hours since the story began" — or days, or minutes; **you decide what one unit
means**, once, at the start.

Numbers sound unromantic, but they're why Chronos can be useful: comparing
"hour 200" to "hour 210" is something it can never get wrong, whereas real-world
dates fall apart the moment your story isn't set on Earth.

You don't have to *read* numbers, though. Tell Chronos your world's calendar —
how many hours in a day, days in a month, months in a year, and what the era is
called — and it translates for you:

| Your world's calendar | What Chronos shows |
| --- | --- |
| 24-hour days, 30-day months, 12-month years, era "AF" | hour 200 → **Year 1, Month 1, Day 9, 08:00 AF** |

Invented calendars are fine — thirteen months, ten-day weeks, whatever your
world uses. And events *before* your starting point are just negative numbers,
so flashbacks and ancient history need no special handling.

**More than one calendar.** Worlds rarely agree on how to count. A book can keep
several reckonings side by side — the Imperial one, the elves' — and you read
the same scenes through whichever you like; the story never changes, only the
dates on it. A calendar can also have a *beginning and an end*, which is what a
destroyed culture's calendar needs: past the year its keepers died out, it stops
dating things and says so, rather than inventing years no one was counting.

Calendars you want again live in a **library**, so you build one once and attach
it to any book — and can share it with the people you write with.

> **One practical note today:** Chronos *shows* you calendar dates, but when
> you record a scene you still give it the plain number. Typing "Day 9" and
> having it understood isn't built yet.

### You don't need to know when it happens

Most of the time you'll sketch a scene long before you've worked out where it
sits on the clock — so **timing is optional**. Write the scene, put it in a
thread, and leave the when for later.

Chronos treats that as a normal part of drafting, not a mistake. Undated scenes
are simply left out of the timing checks, and your book stays "consistent". It
keeps a running to-do list of what still needs a time.

Better, it works out where each undated scene *could* go. Because your thread
already says what comes before and after, the dated scenes around it pin it
down:

> **The Harbor Exchange** — no time set yet
> must fall between **Day 2** (when Aldric Departs ends) and **Day 9** (when
> The Coronation begins)

And if the scenes around it leave **no room at all** — the one before ends after
the one after begins — it tells you, because then there's no time the scene
could possibly happen. That's a genuine knot in the story, and it's one you'd
have almost no chance of spotting by hand when the two scenes belong to
different threads.

---

## What Chronos checks for you

Three continuity questions, asked constantly.

**1. Can a character be in two places at once?** No. If Aldric is riding from
Highkeep between hours 0 and 24, he cannot also be seen at Emberport at hour 10.
Chronos catches it and tells you exactly which two scenes disagree.

*(Two scenes at the **same** place overlapping is fine — that's just two things
happening in one location.)*

**2. Do the threads run forwards?** Within a plotline, each scene must end
before the next begins. List them out of order and Chronos names the offending
pair.

**3. Does every thread reach the ending?** All plotlines must finish at the
terminus. If one wanders off, Chronos says which one and where it stopped.

### It warns; it never blocks

**This is the most important thing to know: Chronos will not stop you writing.**

If you record something contradictory, it saves anyway. Your book is simply
marked **"conflicted"** — and that word is a link. Click it (or **Report** in
the book's own header) for the full list, whenever you want:

> **The Ember Pact** — 2 problems · 1 scene still waiting for a time
>
> **A character in two places at once**
> - **Aldric At Emberport** — *The Witness's Tale*, *The Knight's Road*
>   'Sir Aldric' cannot be here and in 'Aldric Departs' at once — that scene is
>   at 'Highkeep' over an overlapping time.

Each problem is listed **once**, however many threads it turns up on, and says
which ones those are — the thing you cannot see from inside any single thread.

Fix it — move the scene, change the location, split the character — and the book
goes back to **"consistent"**.

This is deliberate. Drafts are messy, you might plan a scene before you've
worked out the timing, and if you're writing with someone else it would be
maddening to have your save rejected because of *their* edit. Chronos reports;
you decide.

Some things *are* refused, but only ones where the request doesn't make sense:
referring to a character who doesn't exist, a scene that ends before it starts,
or deleting a scene that a thread still depends on.

---

## Your cast lives next door

Characters, items and locations aren't stored in Chronos. They're articles in
the companion **Akasha** — a small wiki where you write them up, link
them to each other, and keep their history.

Chronos only *points* at them, and it refuses to point at something that doesn't
exist. So you can't accidentally invent "Aldrik" in one scene and "Aldric" in
another: if you haven't written the character up, Chronos won't accept the
scene.

The upside is one shared canon. Sir Aldric is one article; every scene he's in
refers to that one entry.

---

## Building a plotline, start to finish

Here's the whole workflow, in the order you'd actually do it.

**Step 1 — Write up your cast and places.** In the wiki, create articles for
your characters, important items, and locations. *(Sir Aldric, Lyra Vane,
Magister Corwin, the Ember Seal, Highkeep, Emberport, the Throne Hall.)*

**Step 2 — Create the book.** Give it a title, and if you'd like readable dates,
describe your world's calendar.

**Step 3 — Add scenes, in any order.** For each one: who's there, what they
carry, where it happens, when it starts and ends, and what happens. You don't
have to add them chronologically — you're building a pool of scenes.

**Step 4 — Draw your threads.** Create a plotline: name it, give it its goals,
and list its scenes in story order. Do the same for each thread.

> The Knight's Road → Aldric Departs, The Harbor Exchange, The Coronation
> The Spy's Shadow → Lyra Infiltrates, The Harbor Exchange, The Coronation
> The Magister's Gambit → Corwin Plots, The Coronation

Notice The Harbor Exchange appears in two threads — that's the meeting, and you
created it just by listing the same scene twice.

**Step 5 — Name the ending.** Mark The Coronation as the terminus. Chronos
checks that every thread ends there.

**Step 6 — Ask how it's holding up.** Request the book's report. Either
everything is consistent, or you get a precise list of what contradicts what.

**Step 7 — Keep going.** Add scenes, reorder threads, move things in time. The
report is always current, so you can check whenever you like — after a writing
session, before a rewrite, whenever a nagging doubt strikes.

---

## Writing with other people

Invite a collaborator to a book and give them a role: **reader** (can look),
**editor** (can change scenes and threads), or **owner** (can also delete and
invite others). You both use the same login you use for the wiki.

If you and a co-author edit the *same* scene at the same time, Chronos won't let
the second save silently erase the first — it stops and shows you that the scene
changed underneath you.

If your separate edits happen to create a contradiction between *different*
scenes, both saves succeed and the book is marked conflicted, with the clash
described. Neither of you gets blocked by the other's work.

---

## What Chronos is not

- **Not a word processor.** It stores what happens in a scene, not your prose.
- **Not a plot generator.** Every event and thread is yours.
- **Not a judge of quality.** "Consistent" means your timeline doesn't
  contradict itself — nothing about whether the story is any good.
- **Visual, up to a point.** The **story map** draws any number of the book's
  threads together — where they split, where they meet, in time order — with
  each scene one line until you click it. It will not tell you whether the
  shape is any good.

---

## In one paragraph

Write up your characters, items and places. Record each scene with its people,
place and timeframe. String scenes into named threads with goals, let threads
share scenes where they meet, and point them all at one ending. Chronos then
watches for the three ways a timeline breaks — someone in two places at once,
scenes in an impossible order, a thread that never arrives — and tells you
plainly what's wrong without ever standing in your way.
