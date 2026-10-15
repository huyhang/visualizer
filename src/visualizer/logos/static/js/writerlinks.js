// The way into the writing page from the reader and the contents page.
//
// The writing page itself is a compiled bundle (frontend/src/logos, served by
// `writer_page.py` for `?mode=write`); all the reader needs is its address,
// and -- for a book with no manuscript yet -- a first chapter to open it on.

import { api } from "./api.js";
import { allSectionIds, availableId, emptyDocument } from "./contents.js";
import { el } from "./dom.js";

export const writerUrl = (base, book, volume, section, draft = null) => {
  const query = { book, volume, section, mode: "write" };
  if (draft) query.draft = draft;
  return `${base}/?${new URLSearchParams(query)}`;
};

function askChapterName() {
  return new Promise((resolve) => {
    const input = el("input", {
      class: "jump-search", value: "Untitled chapter", maxlength: "120", required: true,
      "aria-label": "Chapter title",
    });
    const dialog = el("dialog", { class: "settings writer-name-dialog" });
    const finish = (answer) => {
      dialog.close();
      dialog.remove();
      resolve(answer);
    };
    const form = el("form", { method: "dialog", onsubmit: (event) => {
      event.preventDefault();
      const name = input.value.trim();
      if (name) finish(name);
    } }, [
      el("div", { class: "settings-head" }, [
        el("h2", { text: "Name the new chapter" }),
        el("button", { class: "icon-btn", type: "button", text: "x",
          "aria-label": "Cancel", onclick: () => finish(null) }),
      ]),
      input,
      el("div", { class: "settings-actions" }, [
        el("button", { class: "btn ghost", type: "button", text: "Cancel", onclick: () => finish(null) }),
        el("button", { class: "btn", type: "submit", text: "Continue" }),
      ]),
    ]);
    dialog.appendChild(form);
    document.body.appendChild(dialog);
    dialog.addEventListener("cancel", (event) => { event.preventDefault(); finish(null); }, { once: true });
    dialog.showModal();
    input.select();
  });
}

/** Start a manuscript: a first volume if there is none, a named chapter, and the writer on it. */
export async function beginWriting(manuscript, base) {
  const title = await askChapterName();
  if (!title) return;
  let volume = manuscript.volumes[manuscript.volumes.length - 1];
  if (!volume) {
    volume = await api.createVolume(manuscript.book, "volume-1", { title: "Volume One", overview: "" });
  }
  const section = availableId(title, allSectionIds(manuscript), "chapter");
  await api.createSection(manuscript.book, volume.id, section, {
    kind: "chapter", title, overview: "", event_ids: [], document: emptyDocument(),
  });
  window.location.href = writerUrl(base, manuscript.book, volume.id, section);
}
