// How a goal reads, wherever it is drawn.
//
// A goal is now shown in two places that are not the same shape: the expanded
// card on the goals page, and the peek panel that opens beside a thread, the
// table or the map. What they must agree on is not the layout but the *words* --
// what "conflicted" is called, which fact is worth a summary line, what an empty
// "Rests on" says. Two copies of that would drift, and the drift would be a goal
// that reads as "needs attention" in one place and "conflicted" in the other.
//
// So the wording lives here and the layout does not. Nothing in this module
// fetches, routes, or decides anything -- the server decides a goal's state, and
// callers pass in what a chip should do.

import { el, expandableText } from "./dom.js";
import { MISSING } from "./goalplacing.js";

const isConflict = (f) => f.severity === "conflict";

const state = (goal) => (goal.status || {}).state || "open";

// What a goal's state is called on screen. The server decides the state; this
// only decides the wording, so the diagram, the list and the panel always agree.
export const STATE_LABEL = {
  achieved: "achieved",
  conflicted: "needs attention",
  open: "open",
};

// The two glyphs a goal is marked with, kept here beside the words for the same
// reason the words are here: a tick meaning "delivered" on the map and a circle
// meaning it on a thread would be two vocabularies for one fact.
//
// A tick is the ordinary sign for "done", which is exactly what a goal with a
// scene behind it is -- and it reads as that at a glance in a way the filled
// circle it replaces never did. The hollow circle keeps its job: not yet.
export const DONE = "✓";
export const TODO = "○";

// The glyph for where a goal stands. `conflicted` gets the tick too: the story
// does arrive at it, and what is wrong with it is said in words beside it
// rather than by withholding the mark.
export const goalMark = (goal) => (goal.achieved_scene ? DONE : TODO);

export function stateChip(goal) {
  const name = state(goal);
  const label = STATE_LABEL[name] || name;
  return el("span", {
    class: `chip state ${name}`,
    text: name === "achieved" ? `${DONE} ${label}` : label,
  });
}

export const stateClass = (goal) => `is-${state(goal)}`;

// The one line a goal shows when there is only room for one: where it lands,
// which is the fact a reader scanning is usually after. It stands in for the
// four facts below, so it says the *most* useful of them rather than a count.
export function summaryLine(goal) {
  if (goal.achieved_scene) return goal.achieved_scene.title;
  return "no scene yet";
}

// Where a goal meets the timeline, said in full: the scene and its date, in
// whichever calendar the page around it is being read in. A goal has no date of
// its own -- it borrows this one -- so this is the only place a goal is dated.
export function whenLine(goal) {
  if (!goal.achieved_scene) return null;
  const { title, when } = goal.achieved_scene;
  return when ? `${title} · ${when}` : title;
}

export function findingLines(goal) {
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
export function goalChips(refs, onSelect, empty) {
  if (!refs || !refs.length) return el("span", { class: "muted", text: empty });
  return el("div", { class: "chip-row" }, refs.map((ref) => (ref.missing
    ? el("span", { class: "chip goal missing", text: ref.title, title: "No longer in this book" })
    : el("button", {
        class: "chip goal link", type: "button", text: ref.title,
        onclick: () => onSelect(ref.id),
      }))));
}

// The four facts the book knows about a goal: what it rests on, what rests on
// it, who is pursuing it and where it lands. `onScene` is optional -- the goals
// page has nowhere to send a scene, while the peek panel can open it.
export function goalFacts(goal, { onGoal, onPlotline, onScene } = {}) {
  return el("dl", { class: "goal-facts" }, [
    el("dt", { text: "Rests on" }),
    el("dd", {}, goalChips(goal.dependencies, onGoal, "Nothing.")),
    el("dt", { text: "Needed by" }),
    el("dd", {}, goalChips(goal.required_by, onGoal, "Nothing yet.")),
    el("dt", { text: "Pursued by" }),
    el("dd", {}, (goal.plotlines || []).length
      ? el("div", { class: "chip-row" }, goal.plotlines.map((p) => el("button", {
          class: "chip link", type: "button", text: p.title,
          title: "Open this plotline", onclick: () => onPlotline && onPlotline(p.id),
        })))
      : el("span", { class: "muted", text: "No thread yet." })),
    el("dt", { text: "Achieved at" }),
    el("dd", {}, achievedAt(goal, onScene)),
  ]);
}

function achievedAt(goal, onScene) {
  const line = whenLine(goal);
  if (!line) return el("span", { class: "muted", text: "No scene yet." });
  if (!onScene) return el("span", { text: line });
  return el("button", {
    class: "chip link", type: "button", text: line,
    title: "Open this scene", onclick: () => onScene(goal.achieved_at),
  });
}

export function description(goal) {
  return goal.description
    ? expandableText(goal.description, { class: "goal-description" })
    : null;
}

// The goals a graph pursues that are not drawn on it, and why not.
//
// Without this a thread serving four goals and marking one reads as a thread
// with one goal: the other three would be chips in the header and marks
// nowhere, and their absence looks exactly like nothing being wrong. Naming
// them turns "why isn't this one on the rail?" into an answered question -- and
// the interesting case, a goal this thread pursues that another thread
// delivers, becomes a fact you can see rather than one you have to notice.
//
// Shared by the thread's timeline and the story map because it is the same
// statement in both, differing only in what "here" means. `null` when there is
// nothing to say: an empty band would be chrome saying nothing.
export function unplacedStrip(unplaced, onGoal, { label = "Not landed on this thread" } = {}) {
  if (!unplaced || !unplaced.length) return null;
  return el("div", { class: "goal-strip" }, [
    el("span", { class: "goal-strip-label muted", text: label }),
    el("ul", { class: "goal-strip-list" }, unplaced.map((g) => el("li", {}, [
      // A dangling id has nothing to open, so it is drawn plainly -- the note
      // beside it is the whole story.
      g.reason === MISSING
        ? el("span", { class: "chip goal missing", text: g.title })
        : el("button", {
            class: "chip goal link", type: "button", text: `${TODO} ${g.title}`,
            title: "Open this goal", onclick: () => onGoal(g.id),
          }),
      el("span", { class: "muted sm goal-strip-note", text: g.note }),
    ]))),
  ]);
}
