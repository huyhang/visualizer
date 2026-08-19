// The "peek" slot: the panel that shows one thing in detail beside whatever you
// were reading — a referenced Akasha article, a scene from somewhere else in
// the book, or a goal one of them names. It owns `#peek` so no view has to,
// which is what lets a finding on the plotline page and a finding inside the
// editor modal both open the same card without threading callbacks through
// three layers.

import { articleCard, eventPeekCard, goalPeekCard } from "./cards.js";
import { $, clear } from "./dom.js";

const slot = () => $("#peek");

export function clearPeek() {
  clear(slot());
}

// A referenced Akasha article (character, item, place).
export function showArticle(book, ref) {
  const node = slot();
  clear(node);
  node.appendChild(articleCard(book, ref, { onClose: clearPeek }));
}

// One scene, in full. `node` may be a story-graph node (which already knows the
// scene's timing and role) or just `{id}` — the card fills in what it was not
// told from the scene itself.
export function showScene(book, node) {
  const host = slot();
  clear(host);
  host.appendChild(eventPeekCard(book, node, {
    showEntity: (ref) => showArticle(book, ref),
    onClose: clearPeek,
  }));
}

// One goal, in full. Opened from a chip on a thread, in the table, in the report
// or on the map — none of which should have to become the goals page to answer
// "what is this goal, and where does it land?".
//
// `calendar` is the reckoning the calling view is being read in, so the date on
// the card is the same date the page behind it is showing. The chips inside
// recurse into this same slot: a goal's prerequisites are goals, and following
// one is reading, not navigating. Everything that leaves the panel — a thread,
// the goals page — is the caller's to decide, because only the caller knows
// what leaving means from where it stands.
export function showGoal(book, goalId, { calendar = null, onPlotline, onOpenInGoals } = {}) {
  const host = slot();
  clear(host);
  host.appendChild(goalPeekCard(book, goalId, {
    calendar,
    onClose: clearPeek,
    onGoal: (id) => showGoal(book, id, { calendar, onPlotline, onOpenInGoals }),
    onScene: (id) => showScene(book, { id }),
    onPlotline,
    onOpenInGoals,
  }));
}
