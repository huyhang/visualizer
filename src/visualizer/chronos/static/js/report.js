// The book's continuity report: everything wrong across all of its threads, on
// one page.
//
// Until this existed the only way to learn what was wrong with a book was to
// open every plotline in turn — and a conflict between two threads was visible
// from either of them, so the writer also had to work out which sightings were
// the same problem. The server does both now (`chronos/book_health.py`): one
// issue per problem, naming every thread that can see it.
//
// Nothing is decided here. The grouping, the headings, the wording, the order
// and the severity all arrive from the server, for the same reason the per-scene
// findings do: the report and the timeline must not end up calling the same rule
// two different things.
//
// It is a route rather than a modal because it is somewhere a writer goes and
// stays — reading down a list, filtering it, and leaving for the scene that
// needs fixing.

import { api } from "./api.js";
import { calendarSwitcher, currentFor } from "./calendarview.js";
import { clear, el, toast } from "./dom.js";
import { entityTitle } from "./entities.js";
import { withArticleTitles } from "./findings.js";
import { showArticle, showScene } from "./peek.js";

// Which thread the reader has narrowed to. "" is all of them.
const ALL = "";

// Whether the "Worth knowing" section is folded away. Remembered like the
// focus-mode toggle is: a writer drafting a book with forty undated scenes
// should not have to fold them again on every visit.
const NOTES_KEY = "chronos.report.notes";

function notesOpen() {
  try {
    return window.localStorage.getItem(NOTES_KEY) !== "closed";
  } catch (e) {
    return true; // unreadable storage is simply no preference
  }
}

function rememberNotes(open) {
  try {
    window.localStorage.setItem(NOTES_KEY, open ? "open" : "closed");
  } catch (e) { /* private mode: the choice just does not outlive the page */ }
}

export async function mountBookReport(container, book, { onBooks, onBook, onScene, onGoal }) {
  clear(container);

  let bookMeta = { title: book };
  try { bookMeta = await api.getBook(book); } catch (e) { /* fall back to the id */ }
  let calendar = currentFor(book, bookMeta.calendars);
  let thread = ALL;

  const results = el("div", { class: "report-results" },
    el("p", { class: "muted", text: "Loading…" }));
  const filter = el("select", { class: "thread-filter", "aria-label": "Show one thread" });
  filter.addEventListener("change", () => { thread = filter.value; render(); });
  // Hidden until the book is known to have a choice worth making, the same way
  // the calendar switcher stays out of a book with one reckoning.
  const filterBar = el("div", { class: "filter-bar", hidden: "" }, [filter]);

  container.appendChild(el("div", { class: "view report-view" }, [
    breadcrumb(bookMeta.title || book, onBooks, onBook),
    el("div", { class: "book-head" }, [
      el("h1", { class: "view-title", text: "Report" }),
      el("span", { class: "muted", text: bookMeta.title || book }),
      // Two of the messages quote ticks, so the reckoning they are written in
      // is a real choice. Re-reads rather than re-labels: the labels are the
      // server's, here as everywhere.
      calendarSwitcher(book, bookMeta.calendars, (chosen) => { calendar = chosen; render(); }),
    ].filter(Boolean)),
    el("p", { class: "view-lead muted", text:
      "Everything the story rules can see across this book's plotlines. A "
      + "problem is listed once, however many threads it shows up on." }),
    filterBar,
    results,
  ]));

  let loaded = false;

  async function render() {
    let body;
    try {
      body = await api.bookIssues(book, { calendar });
    } catch (e) {
      clear(results);
      results.appendChild(el("p", { class: "empty", text: "Could not load the report." }));
      toast(e.message || "Could not load the report.", true);
      return;
    }
    if (!loaded) {
      fillFilter(filter, body.plotlines);
      filterBar.hidden = body.plotlines.length < 2;
      loaded = true;
    }
    clear(results);
    // Narrowing to a thread from the rollup drives the same control the reader
    // could have used, rather than a second, invisible piece of state.
    const onThread = (id) => {
      thread = id;
      filter.value = id;
      render();
    };
    const deps = {
      onScene, onGoal, onThread,
      onNotes: (open) => { rememberNotes(open); render(); },
    };
    for (const node of sections(book, body, thread, deps)) results.appendChild(node);
  }

  render();
}

// -- the page ----------------------------------------------------------------

function sections(book, body, thread, deps) {
  const problems = narrow(body.problems, thread);
  const notes = narrow(body.notes, thread);
  const out = [verdict(problems, notes, thread)];
  for (const group of problems) out.push(groupBlock(book, group, deps));
  if (notes.length) {
    const open = notesOpen();
    out.push(notesHeading(notes, open, deps.onNotes));
    if (open) for (const group of notes) out.push(groupBlock(book, group, deps));
  }
  // Last, because it answers "which thread do I open first" — a question you
  // ask after reading what is wrong, not before.
  if (body.plotlines.length > 1) out.push(rollup(body.plotlines, thread, deps.onThread));
  return out;
}

// The fold for the notes. Its label carries the count, so folding never hides
// the fact that there is something there.
function notesHeading(notes, open, onNotes) {
  const total = count(notes);
  return el("div", { class: "report-heading-row" }, [
    el("h2", { class: "report-heading", text: "Worth knowing" }),
    el("button", {
      class: "expand-toggle", type: "button",
      text: open ? "Hide" : `Show ${total} note${total === 1 ? "" : "s"}`,
      onclick: () => onNotes(!open),
    }),
  ]);
}

// Which thread to open first. The count is this report's own — including the
// whole-thread verdicts the plotline table's Health column has never shown —
// so the column says so rather than inviting a comparison it would lose.
function rollup(plotlines, thread, onThread) {
  const sorted = [...plotlines].sort(
    (a, b) => (b.problems - a.problems) || a.title.localeCompare(b.title),
  );
  const row = (pl) => el("tr", {
    class: `pl-row${pl.id === thread ? " is-current" : ""}`,
    onclick: () => onThread(pl.id === thread ? "" : pl.id),
  }, [
    el("td", {}, el("span", { class: "pl-name", text: pl.title })),
    el("td", {}, pl.problems
      ? el("span", { class: "health-flag", text: String(pl.problems) })
      : el("span", { class: "muted", text: "—" })),
  ]);
  return el("section", { class: "report-rollup" }, [
    el("h2", { class: "report-heading", text: "By plotline" }),
    el("p", { class: "muted rollup-hint", text: thread
      ? "Showing one thread — click it again for all of them."
      : "Most problems first. Click a thread to narrow the report to it." }),
    el("div", { class: "table-wrap" }, el("table", { class: "pl-table" }, [
      el("thead", {}, el("tr", {}, [
        el("th", { text: "Plotline" }),
        el("th", { text: "Problems here" }),
      ])),
      el("tbody", {}, sorted.map(row)),
    ])),
  ]);
}

// The one line the writer reads first. Counted from what is on screen, so it
// still answers the question after the thread filter has narrowed it.
function verdict(problems, notes, thread) {
  const shown = count(problems);
  const undated = count(notes, (i) => i.code === "UNSCHEDULED");
  if (!shown && !undated) {
    return el("p", { class: "report-verdict sound", text: thread
      ? "Nothing to fix on this plotline."
      : "Nothing to fix — this book holds together." });
  }
  // Only the number that means "fix something" takes the alarming colour; the
  // to-do tally sits beside it in the quiet one, because it is not a fault.
  const tallies = [];
  if (shown) {
    tallies.push(el("span", { class: "tally conflict" },
      [el("strong", { text: String(shown) }), ` problem${shown === 1 ? "" : "s"}`]));
  }
  if (undated) {
    tallies.push(el("span", { class: "tally" },
      [el("strong", { text: String(undated) }),
        ` scene${undated === 1 ? "" : "s"} still waiting for a time`]));
  }
  const line = el("p", { class: "report-verdict" }, tallies[0]);
  if (tallies[1]) {
    line.appendChild(el("span", { class: "tally-sep", text: "·", "aria-hidden": "true" }));
    line.appendChild(tallies[1]);
  }
  return line;
}

function count(groups, keep = () => true) {
  return groups.reduce((n, g) => n + g.issues.filter(keep).length, 0);
}

// One kind of problem, as a card. Severity is the card's left edge and the tint
// of its tally — not a glyph on every row: within a group every row has the same
// severity, so a mark repeated down the list only says what the heading said.
function groupBlock(book, group, { onScene, onGoal }) {
  return el("section", { class: `issue-group ${group.severity}` }, [
    el("h3", { class: "issue-group-title" }, [
      el("span", { class: "issue-group-name", text: group.title }),
      el("span", { class: "issue-count", text: String(group.issues.length) }),
    ]),
    el("div", { class: "issue-list" },
      group.issues.map((issue) => issueRow(book, issue, { onScene, onGoal }))),
  ]);
}

function issueRow(book, issue, { onScene, onGoal }) {
  const message = el("p", { class: "issue-text", text: issue.message });
  // The message quotes article ids; swap in their titles where the reader holds
  // the grant, exactly as the timeline does.
  withArticleTitles(book, issue, message);
  const others = issue.goals || [];
  return el("div", { class: "issue" }, [
    el("div", { class: "issue-head" }, [
      // Where the problem is, said before what it is: the message is phrased
      // from this scene's point of view ("this scene has not ended when…")
      // and only reads correctly next to it. A goal finding says "this goal…"
      // instead, and needs its anchor named for exactly the same reason —
      // without it the row reads "No scene achieves this goal yet" about
      // nothing in particular.
      issue.scene ? sceneLink(book, issue, { onScene }) : null,
      issue.goal ? goalLink(issue.goal, { onGoal }) : null,
      ...issue.plotlines.map((pl) => threadLink(pl, issue, { onScene })),
    ].filter(Boolean)),
    message,
    issue.events.length || others.length || issue.refs.length
      ? el("div", { class: "issue-links" }, [
        ...issue.events.map((other) => el("button", {
          class: "banner-link", type: "button", text: other.title,
          title: "Look at this scene",
          // The peek panel rather than a jump: the other end of a problem is
          // often on a thread the reader is not looking at, and a card beside
          // the report keeps them in the list they are working down.
          onclick: () => showScene(book, { id: other.id }),
        })),
        // The other goals the message names — the one this rests on, or the
        // ring it loops around. Same idea as the scenes above: the prose says
        // them, and these take you to them.
        ...others.map((other) => goalChip(other, { onGoal })),
        // The people and places the message names, as things you can open.
        // The message already says them in prose; what the prose cannot do is
        // take you to the article to check what it claims.
        ...issue.refs.map((ref) => articleChip(book, ref)),
      ])
      : null,
  ].filter(Boolean));
}

// One Akasha article named by an issue. Its title arrives from the same
// memoised, permission-checked proxy the message substitution uses — so a
// reader without the grant is left with the id, which is the honest outcome.
function articleChip(book, ref) {
  const chip = el("button", {
    class: "chip ref-chip", type: "button", text: ref.id,
    title: "Open this article",
    onclick: () => showArticle(book, ref),
  });
  entityTitle(book, ref).then((title) => {
    if (title && title !== ref.id) chip.textContent = title;
  });
  return chip;
}

// The scene, as somewhere to go. On a thread it opens that thread's timeline at
// this scene; belonging to none, it can only be looked at.
function sceneLink(book, issue, { onScene }) {
  const plotline = (issue.plotlines[0] || {}).id || null;
  return el("button", {
    class: "issue-scene", type: "button", text: issue.scene.title,
    title: plotline ? "Open this scene on its plotline" : "Look at this scene",
    onclick: () => (plotline ? onScene(plotline, issue.scene.id) : showScene(book, issue.scene)),
  });
}

// The goal a message is said about, as somewhere to go: the goals view, opened
// on it, where what it rests on and what the book does about it are answered.
function goalLink(goal, { onGoal }) {
  return el("button", {
    class: "issue-goal", type: "button", text: goal.title,
    title: "Open this goal",
    onclick: () => onGoal && onGoal(goal.id),
  });
}

function goalChip(goal, { onGoal }) {
  return el("button", {
    class: "chip goal link", type: "button", text: goal.title,
    title: "Open this goal",
    onclick: () => onGoal && onGoal(goal.id),
  });
}

function threadLink(plotline, issue, { onScene }) {
  return el("button", {
    class: "chip thread-chip", type: "button", text: plotline.title,
    title: "Open this plotline",
    onclick: () => onScene(plotline.id, issue.scene ? issue.scene.id : null),
  });
}

// -- narrowing to one thread --------------------------------------------------

// An issue belonging to no thread — no ending designated, a scene nothing
// lists — is not about the thread being asked after, so it stands down while
// the filter is on.
function narrow(groups, thread) {
  if (!thread) return groups;
  return groups
    .map((g) => ({ ...g, issues: g.issues.filter((i) => i.plotlines.some((p) => p.id === thread)) }))
    .filter((g) => g.issues.length);
}

function fillFilter(select, plotlines) {
  select.appendChild(el("option", { value: ALL, text: "All plotlines" }));
  for (const pl of plotlines) {
    select.appendChild(el("option", { value: pl.id, text: pl.title }));
  }
  select.value = ALL;
}

function breadcrumb(bookTitle, onBooks, onBook) {
  return el("nav", { class: "crumbs" }, [
    el("a", { href: "#/", text: "Books", onclick: (e) => { e.preventDefault(); onBooks(); } }),
    el("span", { class: "sep", text: "›" }),
    el("a", { href: "#/", text: bookTitle, onclick: (e) => { e.preventDefault(); onBook(); } }),
    el("span", { class: "sep", text: "›" }),
    el("span", { text: "Report" }),
  ]);
}
