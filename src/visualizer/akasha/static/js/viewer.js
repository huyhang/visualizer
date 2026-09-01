// Read view: renders a document as a Wikipedia-style article — heading, wikitext
// body with live links, and an infobox of the remaining facts.

import { el, clear } from "./dom.js";
import { splitArticle, factValueToInput } from "./article.js";
import { renderInto } from "./wikitext.js";
import { parseTarget, resolveTarget } from "./links.js";
import { crumbs } from "./views.js";

export async function renderArticle(container, { db, col, id, doc, rev, titles }, handlers) {
  clear(container);
  container.hidden = false;
  const article = splitArticle(doc, id);
  const scope = { db, col };

  container.appendChild(_toolbar({ titles, title: article.title, rev }, handlers));
  container.appendChild(el("h1", { class: "article-title", text: article.title }));
  container.appendChild(el("div", { class: "article-meta", text: `${db} / ${col} / ${id} · revision ${rev}` }));

  if (article.facts.length) container.appendChild(_infobox(article));

  const bodyEl = el("div", { class: "article-body" });
  container.appendChild(bodyEl);
  if (article.body) {
    await renderInto(bodyEl, article.body, {
      scope, resolveTarget, parseTarget,
      onNavigate: (target) => handlers.onNavigate(target),
    });
  } else {
    bodyEl.appendChild(el("p", { class: "muted", text: "This article has no body yet." }));
  }
}

// The trail is for *going* somewhere — readable names, and every ancestor a
// link. The literal address stays in the meta line below the heading, which is
// where you look when you need the slug to write a [[link]] with.
function _toolbar({ titles, title, rev }, handlers) {
  return el("div", { class: "pane-toolbar" }, [
    crumbs([
      { label: "Home", onClick: handlers.onHome },
      { label: titles.database, onClick: handlers.onDatabase },
      { label: titles.collection, onClick: handlers.onCollection },
      { label: title },
    ]),
    el("span", { class: "spacer" }),
    // Grouped rather than loose beside the trail: on a phone the four of them
    // move to a line of their own, and four siblings in a wrapping row cannot
    // be moved together. How long the trail is then stops deciding how many
    // buttons end up stranded on a second row.
    el("div", { class: "pane-actions" }, [
      el("button", { class: "btn sm", text: "Edit", onclick: () => handlers.onEdit() }),
      el("button", { class: "btn sm secondary", text: "History", onclick: () => handlers.onHistory() }),
      el("button", { class: "btn sm secondary", text: "Share", onclick: () => handlers.onShare() }),
      el("button", { class: "btn sm danger", text: "Delete", onclick: () => handlers.onDelete(rev) }),
    ]),
  ]);
}

function _infobox(article) {
  const rows = article.facts.map(({ key, value }) => {
    const dd = el("dd");
    if (Array.isArray(value)) value.forEach((v) => dd.appendChild(el("span", { class: "chip", text: String(v) })));
    else dd.textContent = factValueToInput(value);
    return el("div", { class: "row" }, [el("dt", { text: key }), dd]);
  });
  return el("aside", { class: "infobox" }, [
    el("h4", { text: article.title }),
    el("dl", {}, rows),
  ]);
}
