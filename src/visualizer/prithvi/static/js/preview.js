// The card beside the map: what the pin's article says, without leaving.
//
// Everything is written with `textContent`. The server already flattened the
// body to plain prose, so there is no wikitext parser here and no `innerHTML`
// anywhere in this UI -- an article body cannot become markup on this page.

export function clearPreview(elements) {
  elements.panel.hidden = true;
  elements.empty.hidden = false;
  elements.remove.hidden = true;
}

export function showPreview(elements, article, canWrite) {
  elements.empty.hidden = true;
  elements.panel.hidden = false;
  elements.eyebrow.textContent = article.collection_title;
  elements.title.textContent = article.title;
  elements.excerpt.textContent = article.excerpt || "This article has no body yet.";
  elements.facts.replaceChildren(...article.facts.map(fact));
  elements.link.href = article.url;
  elements.link.hidden = false;
  elements.remove.hidden = !canWrite;
}

// A pin whose article has been deleted in Akasha, or that this reader may not
// see. Both land here: the panel says what it can and offers no dead link.
export function showUnavailable(elements, name, canWrite) {
  elements.empty.hidden = true;
  elements.panel.hidden = false;
  elements.eyebrow.textContent = "Article unavailable";
  elements.title.textContent = name;
  elements.excerpt.textContent =
    "This article no longer exists, or is not one you can read.";
  elements.facts.replaceChildren();
  elements.link.removeAttribute("href");
  elements.link.hidden = true;
  // Still removable: a pin pointing at nothing is exactly the one a writer
  // most wants to clear off the map.
  elements.remove.hidden = !canWrite;
}

function fact({ key, value }) {
  const row = document.createElement("div");
  const term = document.createElement("dt");
  term.textContent = key;
  const detail = document.createElement("dd");
  detail.textContent = value;
  row.append(term, detail);
  return row;
}
