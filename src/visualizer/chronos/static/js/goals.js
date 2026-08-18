// The goals view for one book: the dependency diagram, and a card per goal.
//
// One request feeds both. `GET /books/{book}/goals` returns every goal already
// read against the rest of the book — what it rests on, what rests on it, which
// threads pursue it, the scene that delivers it, how deep it sits and what is
// wrong with it — so the diagram and the list are two readings of the same
// answer and cannot disagree. It is also why there is no paging here: a
// dependency graph is only legible whole.
//
// Selecting a goal is a URL (`#/<book>/~goals/<goal>`), not a mode: a writer
// pointing someone at "the one the ending rests on" should be able to send them
// a link, and a chip on a plotline links straight to the goal it names.

import { api } from "./api.js";
import { clear, el, expandableText, toast } from "./dom.js";
import { drawGoalGraph } from "./goalgraph.js";
import { openGoalForm } from "./goalform.js";

const isConflict = (f) => f.severity === "conflict";

function breadcrumb(bookTitle, { onBooks, onBook }) {
  return el("nav", { class: "crumbs" }, [
    el("a", { href: "#/", text: "Books", onclick: (e) => { e.preventDefault(); onBooks(); } }),
    el("span", { class: "sep", text: "›" }),
    el("a", { href: "#/", text: bookTitle, onclick: (e) => { e.preventDefault(); onBook(); } }),
    el("span", { class: "sep", text: "›" }),
    el("span", { text: "Goals" }),
  ]);
}

// What a goal's state is called on screen. The server decides the state; this
// only decides the wording, so the diagram and the card always agree.
const STATE_LABEL = {
  achieved: "achieved",
  conflicted: "needs attention",
  open: "open",
};

function stateChip(goal) {
  const state = (goal.status || {}).state || "open";
  return el("span", { class: `chip state ${state}`, text: STATE_LABEL[state] || state });
}

function findingLines(goal) {
  const findings = (goal.status || {}).findings || [];
  if (!findings.length) return null;
  return el("div", { class: "findings" }, findings.map((f) => el("div", {
    class: `finding ${isConflict(f) ? "conflict" : "hint"}`,
  }, [
    el("span", { class: "finding-mark", text: isConflict(f) ? "!" : "i", "aria-hidden": "true" }),
    el("span", { class: "finding-text", text: f.message }),
  ])));
}

// A row of goal chips that select the goal they name. `missing` ones are drawn
// plainly and do not link: there is nothing to open, which the finding beside
// them already explains.
function goalChips(refs, onSelect, empty) {
  if (!refs.length) return el("span", { class: "muted", text: empty });
  return el("div", { class: "chip-row" }, refs.map((ref) => (ref.missing
    ? el("span", { class: "chip goal missing", text: ref.title, title: "No longer in this book" })
    : el("button", {
        class: "chip goal link", type: "button", text: ref.title,
        onclick: () => onSelect(ref.id),
      }))));
}

// The one line a closed card shows, after its name and state: where the goal
// lands, which is the fact a reader scanning the list is usually after. It
// stands in for the four rows inside, so it says the *most* useful of them
// rather than a count of all of them.
function summaryLine(goal) {
  if (goal.achieved_scene) return goal.achieved_scene.title;
  return "no scene yet";
}

// One goal. Closed, it is a single row; open, it is everything the book knows
// about it.
//
// Open **is** selected, and selected is the URL -- so the diagram and the list
// are one control rather than two that have to be kept in step, and a link to a
// goal still means what it has always meant. One at a time follows from that:
// there is one selection, and it is in the address bar.
function goalCard(book, goal, { selected, canWrite, onSelect, onPlotline, onChanged, goals }) {
  const open = goal.id === selected;
  const head = el("button", {
    class: "goal-head", type: "button",
    "aria-expanded": open ? "true" : "false",
    title: open ? "Close this goal" : "Open this goal",
    // Closing goes back to the plain goals URL, so the address bar never claims
    // a goal is selected when none is showing.
    onclick: () => onSelect(open ? null : goal.id),
  }, [
    el("span", { class: "twisty", text: open ? "▾" : "▸", "aria-hidden": "true" }),
    el("span", { class: "card-title", text: goal.name }),
    stateChip(goal),
    el("span", { class: "goal-summary muted", text: summaryLine(goal) }),
  ]);

  if (!open) {
    return el("article", {
      class: `card goal-card is-${(goal.status || {}).state || "open"}`,
      id: `goal-${goal.id}`,
    }, head);
  }

  return el("article", {
    // `is-expanded`, not `is-open`: `is-open` is already the *state* of a goal
    // no scene delivers yet, and one class cannot mean two things.
    class: `card goal-card is-expanded is-selected is-${(goal.status || {}).state || "open"}`,
    id: `goal-${goal.id}`,
  }, [
    el("div", { class: "goal-head-row" }, [
      head,
      canWrite ? el("button", {
        class: "icon-btn sm", type: "button", text: "✎", title: "Edit this goal",
        onclick: () => openGoalForm(book, goal, {
          goals, onDone: onChanged, onDeleted: onChanged,
        }),
      }) : null,
    ].filter(Boolean)),
    goal.description ? expandableText(goal.description, { class: "goal-description" }) : null,
    el("dl", { class: "goal-facts" }, [
      el("dt", { text: "Rests on" }),
      el("dd", {}, goalChips(goal.dependencies, onSelect, "Nothing.")),
      el("dt", { text: "Needed by" }),
      el("dd", {}, goalChips(goal.required_by, onSelect, "Nothing yet.")),
      el("dt", { text: "Pursued by" }),
      el("dd", {}, goal.plotlines.length
        ? el("div", { class: "chip-row" }, goal.plotlines.map((p) => el("button", {
            class: "chip link", type: "button", text: p.title,
            title: "Open this plotline", onclick: () => onPlotline(p.id),
          })))
        : el("span", { class: "muted", text: "No thread yet." })),
      el("dt", { text: "Achieved at" }),
      el("dd", {}, goal.achieved_scene
        ? el("span", { text: `${goal.achieved_scene.title} · ${goal.achieved_scene.when}` })
        : el("span", { class: "muted", text: "No scene yet." })),
    ]),
    findingLines(goal),
  ].filter(Boolean));
}

// The cards in the order the diagram reads: prerequisites first, then what
// rests on them. The server returns goals by id, which is the right answer for
// a machine and an arbitrary one here -- a reader scrolling the list should
// meet a goal after the goals it depends on, not after the ones whose slug
// happens to sort earlier.
const inReadingOrder = (goals) =>
  [...goals].sort((a, b) => (a.depth - b.depth) || a.name.localeCompare(b.name));

// Whether the card's top edge is somewhere the reader can already see.
function inView(node) {
  const box = node.getBoundingClientRect();
  return box.top >= 0 && box.top <= (window.innerHeight || 0);
}

const matches = (goal, query) => {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  const text = `${goal.name} ${goal.id} ${goal.description}`.toLowerCase();
  return words.every((word) => text.includes(word));
};

export async function mountGoals(container, book, {
  goal = null, onBooks, onBook, onSelect, onPlotline,
} = {}) {
  clear(container);
  let bookMeta = { title: book };
  try { bookMeta = await api.getBook(book); } catch (e) { /* fall back to the id */ }
  const canWrite = Boolean((bookMeta.permissions || {}).write);

  const filterBox = el("input", {
    type: "search", class: "filter-box", placeholder: "Filter goals…", autocomplete: "off",
  });
  const diagram = el("div", { class: "goal-diagram" });
  const list = el("div", { class: "goal-list" }, el("p", { class: "muted", text: "Loading…" }));

  container.appendChild(el("div", { class: "view goals-view" }, [
    breadcrumb(bookMeta.title || book, { onBooks, onBook }),
    el("div", { class: "book-head" }, [
      el("h1", { class: "view-title", text: "Goals" }),
      canWrite ? el("button", {
        class: "btn sm", type: "button", text: "+ New goal",
        onclick: () => openGoalForm(book, null, { goals, onDone: reload }),
      }) : null,
    ].filter(Boolean)),
    el("p", { class: "view-lead", text:
      "What this book is trying to bring about. A goal is drawn below everything "
      + "it rests on, so the diagram reads downward: earlier at the top. Goals "
      + "that neither rest on anything nor carry anything sit together above it." }),
    el("div", { class: "filter-bar" }, filterBox),
    diagram,
    list,
  ]));

  let goals = [];

  // The diagram always shows the whole graph, filter or no filter: hiding half
  // the nodes would leave edges pointing at nothing, and the filter is for
  // finding a goal, not for slicing the graph. It is the *list* that narrows.
  function render() {
    const query = filterBox.value.trim();
    clear(diagram);
    clear(list);
    if (!goals.length) {
      list.appendChild(el("p", { class: "empty", text:
        canWrite
          ? "No goals yet. Name one, and the threads can start pointing at it."
          : "This book has no goals yet." }));
      return;
    }
    diagram.appendChild(drawGoalGraph(goals, { selected: goal, onPick: onSelect }));

    const shown = inReadingOrder(goals.filter((g) => matches(g, query)));
    if (!shown.length) {
      list.appendChild(el("p", { class: "empty", text: "No goals match your filter." }));
      return;
    }
    for (const each of shown) {
      list.appendChild(goalCard(book, each, {
        selected: goal, canWrite, onSelect, onPlotline, onChanged: reload, goals,
      }));
    }
  }

  async function reload() {
    try {
      goals = (await api.listGoals(book)).goals;
    } catch (e) {
      clear(list);
      list.appendChild(el("p", { class: "empty", text: "Could not load goals." }));
      toast(e.message || "Could not load goals.", true);
      return;
    }
    render();
    // Arriving on a link to one goal should land on it, not at the top of a
    // list it happens to be in the middle of. Only when it is off screen: a
    // writer who just clicked a card open is already looking at it, and moving
    // the page under them would be the opposite of helpful.
    if (goal) {
      const card = container.querySelector(`#goal-${CSS.escape(goal)}`);
      if (card && !inView(card)) card.scrollIntoView({ block: "center" });
    }
  }

  let debounce = null;
  filterBox.addEventListener("input", () => {
    clearTimeout(debounce);
    debounce = setTimeout(render, 200);
  });

  // The diagram is laid out in pixels against the reader's text size, so it has
  // to be drawn again when that changes. The font control sets the root font
  // size (see fontscale.js), which is the one thing worth watching for: the
  // cards below reflow by themselves, being ordinary HTML.
  if (typeof MutationObserver === "function") {
    new MutationObserver(render).observe(document.documentElement, {
      attributes: true, attributeFilter: ["style"],
    });
  }

  await reload();
}
