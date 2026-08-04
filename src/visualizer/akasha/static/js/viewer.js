// Read view: renders a document as a Wikipedia-style article — heading, wikitext
// body with live links, and an infobox of the remaining facts.

import { el, clear } from "./dom.js";
import { splitArticle, factValueToInput } from "./article.js";
import { renderInto } from "./wikitext.js";
import { parseTarget, resolveTarget } from "./links.js";

export async function renderArticle(container, { db, col, id, doc, rev }, handlers) {
  clear(container);
  container.hidden = false;
  const article = splitArticle(doc, id);
  const scope = { db, col };

  container.appendChild(_toolbar({ db, col, id, rev }, handlers));
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

function _toolbar({ db, col, id, rev }, handlers) {
  return el("div", { class: "pane-toolbar" }, [
    el("span", { class: "crumbs" }, [
      el("span", { text: db }), el("span", { class: "sep", text: "›" }),
      el("span", { text: col }), el("span", { class: "sep", text: "›" }),
      el("span", { text: id }),
    ]),
    el("span", { class: "spacer" }),
    el("button", { class: "btn sm", text: "Edit", onclick: () => handlers.onEdit() }),
    el("button", { class: "btn sm secondary", text: "History", onclick: () => handlers.onHistory() }),
    el("button", { class: "btn sm secondary", text: "Share", onclick: () => handlers.onShare() }),
    el("button", { class: "btn sm danger", text: "Delete", onclick: () => handlers.onDelete(rev) }),
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
