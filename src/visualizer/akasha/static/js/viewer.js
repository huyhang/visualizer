// Read view: renders a document as a Wikipedia-style article — heading, wikitext
// body with live links, and an infobox of the remaining facts.

import { el, clear } from "./dom.js";
import { splitArticle, factValueToInput } from "./article.js";
import { createImageFigure, hydrateImages, renderInto } from "./wikitext.js";
import { parseTarget, resolveTarget } from "./links.js";
import { openImageLightbox, resolveMedia } from "./media.js";
import { crumbs } from "./views.js";

export async function renderArticle(container, { db, col, id, doc, rev, titles }, handlers) {
  clear(container);
  container.hidden = false;
  const article = splitArticle(doc, id);
  const scope = { db, col };

  container.appendChild(_toolbar({ titles, title: article.title, rev }, handlers));
  container.appendChild(el("h1", { class: "article-title", text: article.title }));
  container.appendChild(el("div", { class: "article-meta", text: `${db} / ${col} / ${id} · revision ${rev}` }));

  const aside = _articleAside(article);
  if (aside) {
    container.appendChild(aside);
    await hydrateImages(aside, {
      resolveMedia: (mediaId) => resolveMedia(db, mediaId),
      onOpenImage: openImageLightbox,
    });
  }

  const bodyEl = el("div", { class: "article-body" });
  container.appendChild(bodyEl);
  if (article.body) {
    await renderInto(bodyEl, article.body, {
      scope, resolveTarget, parseTarget,
      onNavigate: (target) => handlers.onNavigate(target),
      resolveMedia: (mediaId) => resolveMedia(db, mediaId),
      onOpenImage: openImageLightbox,
    });
  } else {
    bodyEl.appendChild(el("p", { class: "muted", text: "This article has no body yet." }));
  }

  const gallery = article.gallery.filter((item) => item.media_id !== article.profileImage);
  if (gallery.length) {
    const galleryGrid = el("div", { class: "article-gallery-grid" }, gallery.map((item) =>
      createImageFigure({
        media_id: item.media_id,
        align: "full",
        width: 100,
        caption: item.caption,
      }, "gallery-image")));
    const gallerySection = el("section", { class: "article-gallery" }, [
      el("h2", { text: "Gallery" }),
      galleryGrid,
    ]);
    container.appendChild(gallerySection);
    await hydrateImages(gallerySection, {
      resolveMedia: (mediaId) => resolveMedia(db, mediaId),
      onOpenImage: openImageLightbox,
    });
  }
}

function _articleAside(article) {
  const children = [];
  if (article.profileImage) {
    const profile = article.gallery.find((item) => item.media_id === article.profileImage);
    children.push(createImageFigure({
      media_id: article.profileImage,
      align: "full",
      width: 100,
      caption: profile?.caption || "",
    }, "profile-image"));
  }
  if (article.facts.length) children.push(_infobox(article));
  return children.length ? el("aside", { class: "article-aside" }, children) : null;
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
  return el("div", { class: "infobox" }, [
    el("h4", { text: article.title }),
    el("dl", {}, rows),
  ]);
}
