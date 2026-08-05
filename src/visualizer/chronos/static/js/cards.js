// Card builders for the plotline view: the event card (collapsed -> enlarged on
// click, back on mouse-leave) and the Akasha article "peek" card that an entity
// reference opens. Kept free of routing/fetching wiring -- callbacks are passed
// in -- so each builder stays small and the behaviour is obvious.

import { el } from "./dom.js";
import { entityTitle, plainBody, resolveEntity } from "./entities.js";

// The human-readable timeframe for an event summary (also used by the timeline
// rail, so it is exported).
export function eventTimeframe(summary) {
  if (!summary.scheduled) return "unscheduled";
  const start = summary.start_label != null ? summary.start_label : summary.start_tick;
  if (summary.end_label != null && summary.end_label !== summary.start_label) {
    return `${start} → ${summary.end_label}`;
  }
  return String(start);
}

function badges(summary) {
  const out = [];
  if (summary.is_terminus) out.push(el("span", { class: "badge terminus", text: "terminus" }));
  else if (summary.is_convergence) out.push(el("span", { class: "badge merge", text: "convergence" }));
  return out;
}

// A clickable reference to an Akasha article. Shows the id first, then swaps in
// the resolved title; clicking opens the article peek card.
function entityChip(book, ref, kind, showEntity) {
  const chip = el("button", {
    class: `entity-chip ${kind}`,
    title: `${kind}: ${ref.id}`,
    text: ref.id,
    onclick: (e) => { e.stopPropagation(); showEntity(ref); },
  });
  entityTitle(book, ref).then((title) => { chip.textContent = title; });
  return chip;
}

function entityGroup(label, book, refs, kind, showEntity) {
  if (!refs || refs.length === 0) return null;
  return el("div", { class: "ev-entities" }, [
    el("span", { class: "ev-entities-label", text: label }),
    el("div", { class: "chip-row" }, refs.map((r) => entityChip(book, r, kind, showEntity))),
  ]);
}

// Fill the enlarged portion of a card from the full event body (fetched once).
function fillDetail(detail, book, event, showEntity) {
  const parts = [];
  if (event.description) {
    parts.push(el("div", { class: "ev-desc" },
      event.description.split(/\n{2,}/).map((p) => el("p", { text: p }))));
  }
  parts.push(entityGroup("Location", book, [event.location], "location", showEntity));
  parts.push(entityGroup("Characters", book, event.characters, "character", showEntity));
  parts.push(entityGroup("Items", book, event.items, "item", showEntity));
  if (!event.description && !event.characters.length && !event.items.length) {
    parts.push(el("p", { class: "muted", text: "No further detail recorded." }));
  }
  detail.replaceChildren(...parts.filter(Boolean));
}

// summary: an expanded-plotline event summary. getFullEvent(id) -> Promise<event>.
// showTime=false lets a caller (the timeline rail) own the timeframe label so it
// isn't shown twice.
export function eventCard(book, summary, { getFullEvent, showEntity, showTime = true }) {
  const loc = el("span", { class: "ev-loc", text: summary.location.id });
  entityTitle(book, summary.location).then((t) => { loc.textContent = t; });

  const head = [];
  if (showTime) head.push(el("span", { class: "ev-time", text: eventTimeframe(summary) }));
  head.push(...badges(summary));

  const detail = el("div", { class: "ev-detail" }, el("p", { class: "muted", text: "Loading…" }));

  const collapse = () => card.classList.remove("expanded");
  // A close button, shown (via CSS) only while expanded: the card now stays open
  // until dismissed, rather than collapsing when the mouse leaves.
  const closeBtn = el("button", {
    class: "ev-close", type: "button", "aria-label": "Close", title: "Close", text: "✕",
    onclick: (e) => { e.stopPropagation(); collapse(); },
  });

  const card = el("article", { class: "event-card", tabindex: "0" }, [
    closeBtn,
    head.length ? el("div", { class: "ev-head" }, head) : null,
    el("h3", { class: "ev-title", text: summary.title }),
    el("div", { class: "ev-loc-line" }, [el("span", { class: "ev-at", text: "at " }), loc]),
    detail,
  ]);

  let loaded = false;
  const expand = () => {
    if (card.classList.contains("expanded")) return;
    card.classList.add("expanded");
    if (loaded) return;
    loaded = true;
    getFullEvent(summary.id)
      .then((event) => fillDetail(detail, book, event, showEntity))
      .catch(() => { detail.replaceChildren(el("p", { class: "muted", text: "Could not load detail." })); loaded = false; });
  };

  card.addEventListener("click", expand);
  card.addEventListener("keydown", (e) => {
    if (e.target !== card) return; // let chips / the close button handle their own keys
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); expand(); }
    if (e.key === "Escape") collapse();
  });
  return card;
}

function factValue(value) {
  if (Array.isArray(value)) {
    return el("div", { class: "chip-row" }, value.map((v) => el("span", { class: "chip", text: String(v) })));
  }
  return el("span", { text: String(value) });
}

// The peek card for a referenced article. ref is the EntityRef we resolved.
export function articleCard(book, ref, { onClose }) {
  const body = el("div", { class: "peek-body" }, el("p", { class: "muted", text: "Loading…" }));
  const card = el("article", { class: "peek-card" }, [
    el("div", { class: "peek-head" }, [
      el("span", { class: "peek-title", text: ref.id }),
      el("button", { class: "icon-btn sm", text: "✕", title: "Close", onclick: onClose }),
    ]),
    el("div", { class: "peek-meta", text: `${ref.database} / ${ref.collection} / ${ref.id}` }),
    body,
  ]);

  resolveEntity(book, ref).then((r) => {
    if (!r.ok) {
      const msg = r.error && r.error.isForbidden
        ? "You do not have permission to read this article."
        : "This reference no longer exists in Akasha.";
      body.replaceChildren(el("p", { class: "muted", text: msg }));
      return;
    }
    const doc = r.article.document || {};
    card.querySelector(".peek-title").textContent = doc.title || ref.id;
    const facts = Object.entries(doc).filter(([k]) => k !== "title" && k !== "body");
    const blocks = [];
    if (facts.length) {
      blocks.push(el("dl", { class: "peek-facts" }, facts.flatMap(([k, v]) => [
        el("dt", { text: k }), el("dd", {}, factValue(v)),
      ])));
    }
    if (doc.body) {
      blocks.push(el("div", { class: "peek-text" },
        plainBody(doc.body).split(/\n{2,}/).map((p) => el("p", { text: p }))));
    }
    if (!blocks.length) blocks.push(el("p", { class: "muted", text: "This article has no content yet." }));
    body.replaceChildren(...blocks);
  });

  return card;
}
