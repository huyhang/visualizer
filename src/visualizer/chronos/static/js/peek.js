// The "peek" slot: the panel that shows one thing in detail beside whatever you
// were reading — a referenced Akasha article, or a scene from somewhere else in
// the book. It owns `#peek` so no view has to, which is what lets a finding on
// the plotline page and a finding inside the editor modal both open the same
// card without threading callbacks through three layers.

import { articleCard, eventPeekCard } from "./cards.js";
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
