// The pieces every browse view is built from: a breadcrumb trail, a heading
// with its action buttons, a grid of cards, a pager, and "3 days ago".
//
// They are plain node factories rather than mounted components — the views own
// their own layout and just assemble these — so each stays testable by eye and
// none of them knows what it is showing.

import { el } from "./dom.js";
import { count } from "./terms.js";

// A trail of links ending in the page you are on. Each entry is
// `{ label, onClick }`; the last one is rendered as plain text, because a link
// to where you already are is a dead end.
export function crumbs(trail) {
  const parts = [];
  trail.forEach((step, i) => {
    if (i) parts.push(el("span", { class: "sep", text: "›" }));
    const last = i === trail.length - 1;
    parts.push(last || !step.onClick
      ? el("span", { text: step.label })
      : el("a", { href: "#", text: step.label, onclick: (e) => { e.preventDefault(); step.onClick(); } }));
  });
  return el("nav", { class: "crumbs", "aria-label": "Breadcrumb" }, parts);
}

// A view heading with its actions on the right. `actions` entries are
// `{ label, onClick, variant }`; a null entry is dropped, so a caller can write
// `canWrite ? {...} : null` and let permission decide whether a button exists.
export function viewHead(title, actions = []) {
  return el("div", { class: "view-head" }, [
    el("h1", { class: "view-title", text: title }),
    el("div", { class: "view-actions" }, actions.filter(Boolean).map((a) =>
      el("button", {
        class: `btn sm ${a.variant || ""}`.trim(),
        type: "button",
        text: a.label,
        onclick: a.onClick,
      }))),
  ]);
}

// A grid of pickable cards. Each card is `{ title, sub, meta, onOpen }`.
export function cardGrid(cards) {
  return el("div", { class: "card-grid" }, cards.map((card) =>
    el("button", { class: "card", type: "button", onclick: card.onOpen }, [
      el("span", { class: "card-title", text: card.title }),
      card.sub ? el("span", { class: "card-sub", text: card.sub }) : null,
      card.meta ? el("span", { class: "card-meta", text: card.meta }) : null,
    ])));
}

// Prev/next around "Page 2 of 5 · 61 articles". Returns nothing at all for a
// single page — a pager that can never be pressed is just noise.
export function pager({ page, pages, total }, term, onPage) {
  if (pages <= 1) return null;
  return el("div", { class: "pager" }, [
    el("button", {
      class: "btn secondary sm", type: "button", text: "‹ Prev",
      disabled: page <= 1 ? "" : null, onclick: () => onPage(page - 1),
    }),
    el("span", { class: "pager-info", text: `Page ${page} of ${pages} · ${count(total, term)}` }),
    el("button", {
      class: "btn secondary sm", type: "button", text: "Next ›",
      disabled: page >= pages ? "" : null, onclick: () => onPage(page + 1),
    }),
  ]);
}

const MINUTE = 60, HOUR = 3600, DAY = 86400;

// A rough "when", in the units a person would use. Anything older than a month
// is given as a date instead, because "63 days ago" is not an improvement on it.
export function timeAgo(iso) {
  if (!iso) return "—";
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return "—";
  const seconds = Math.max(0, (Date.now() - then) / 1000);
  if (seconds < MINUTE) return "just now";
  if (seconds < HOUR) return `${Math.floor(seconds / MINUTE)}m ago`;
  if (seconds < DAY) return `${Math.floor(seconds / HOUR)}h ago`;
  if (seconds < 30 * DAY) return `${Math.floor(seconds / DAY)}d ago`;
  return new Date(then).toLocaleDateString();
}
