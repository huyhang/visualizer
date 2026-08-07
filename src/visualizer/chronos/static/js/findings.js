// Rendering for the per-scene findings Chronos attaches to an expanded plotline.
// No rules live here: severity, wording and the problem count all come from the
// server (see chronos/plotline_health.py), so the read view, the editor and the
// preview all say exactly the same thing.

import { el } from "./dom.js";
import { entityTitle } from "./entities.js";

const isConflict = (f) => f.severity === "conflict";

export function conflictCount(status) {
  return (status && status.conflicts) || 0;
}

// Does this scene have something wrong with it (as opposed to a hint)?
export function hasConflict(summary) {
  return (summary.findings || []).some(isConflict);
}

// The class the timeline rail dot / editor row takes on, so a problem is
// visible before anything is read.
export function markerClass(summary) {
  if (hasConflict(summary)) return " has-conflict";
  if ((summary.findings || []).length) return " has-hint";
  return "";
}

// A finding's message quotes Akasha articles by slug, because the rules module
// cannot see Akasha and the reader may not be allowed to. Swap each `'slug'` for
// `'Title'` once the (memoised, permission-checked) proxy answers — and leave the
// slug alone when it refuses, which is the right outcome for someone without the
// grant. Exact match including the quotes, so a slug can never rewrite part of
// another word.
function withArticleTitles(book, finding, node) {
  for (const ref of finding.refs || []) {
    entityTitle(book, ref).then((title) => {
      if (!title || title === ref.id) return;
      node.textContent = node.textContent.split(`'${ref.id}'`).join(`'${title}'`);
    });
  }
}

// One finding as a chip. `onJump(eventId)` (optional) turns the scenes it names
// into links, so "X has not ended when this begins" can take you to X.
function findingChip(book, finding, onJump) {
  const kind = isConflict(finding) ? "conflict" : "hint";
  const text = el("span", { class: "finding-text", text: finding.message });
  withArticleTitles(book, finding, text);
  const chip = el("div", { class: `finding ${kind}` }, [
    el("span", { class: "finding-mark", text: isConflict(finding) ? "!" : "i", "aria-hidden": "true" }),
    text,
  ]);
  for (const other of finding.events || []) {
    if (!onJump) break;
    chip.appendChild(el("button", {
      class: "finding-jump", type: "button", text: "show",
      title: `Go to ${other}`,
      onclick: (e) => { e.stopPropagation(); onJump(other); },
    }));
  }
  return chip;
}

// Every finding on one scene, or null when it is sound.
export function findingList(book, summary, { onJump } = {}) {
  const findings = summary.findings || [];
  if (!findings.length) return null;
  return el("div", { class: "findings" }, findings.map((f) => findingChip(book, f, onJump)));
}

// Whole-thread verdicts that no single scene can carry: a broken continuation
// chain, or a thread that never reaches the book's ending. Ordering is left out
// — it is already marked on the scenes themselves.
export function verdictNotes(status, events = []) {
  if (!status) return null;
  const notes = [];
  const continuation = status.continuation || {};
  const terminus = status.ends_at_terminus || {};
  if (continuation.state === "conflicted") notes.push(continuation.message);
  // Only when the book actually has an ending designated: otherwise every
  // thread in the book would carry the same complaint, which says nothing.
  if (terminus.state === "conflicted" && (terminus.evidence || {}).terminus) {
    // Name the scene the way the timeline does. Its title is Chronos's own data
    // and is already in hand -- no need to say "it ends at 'aldric-departs'".
    const last = events.find((e) => e.id === terminus.evidence.last_event);
    const name = last ? last.title : terminus.evidence.last_event;
    notes.push(`${terminus.message} It ends at '${name}'.`);
  }
  if (!notes.length) return null;
  return el("div", { class: "findings" }, notes.map((message) => el("div", { class: "finding hint" }, [
    el("span", { class: "finding-mark", text: "i", "aria-hidden": "true" }),
    el("span", { class: "finding-text", text: message }),
  ])));
}

// A summary line for the whole thread: how many problems, and where they are.
// Returns null for a sound thread — a green "all good" banner on every screen
// is noise, and its absence is already the signal.
export function problemBanner(events, status, { onJump } = {}) {
  const count = conflictCount(status);
  if (!count) return null;
  const scenes = events.filter(hasConflict);
  return el("div", { class: "banner conflict" }, [
    el("div", { class: "banner-head" }, [
      el("span", { class: "banner-mark", text: "!", "aria-hidden": "true" }),
      el("strong", { text: `${count} problem${count === 1 ? "" : "s"} in this plotline` }),
    ]),
    el("div", { class: "banner-body" }, scenes.map((s) => el("button", {
      class: "banner-link", type: "button", text: s.title,
      title: "Go to this scene",
      onclick: () => onJump && onJump(s.id),
    }))),
  ]);
}
