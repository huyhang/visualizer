// Article-specific attachments. Media metadata remains in the world library;
// this component owns only order, caption, and profile selection.

import { clear, el, toast } from "./dom.js";
import { resolveMedia } from "./media.js";

export function createGalleryEditor({ db, gallery, profileImage, onChoose, canDetach }) {
  return new GalleryEditor(db, gallery, profileImage, onChoose, canDetach);
}

class GalleryEditor {
  constructor(db, gallery, profileImage, onChoose, canDetach) {
    this.db = db;
    this.items = gallery.map((item) => ({ ...item }));
    this.profileImage = this.items.some((item) => item.media_id === profileImage)
      ? profileImage
      : null;
    this.onChoose = onChoose;
    this.canDetach = canDetach;
    this.list = el("div", { class: "gallery-editor-list" });
    this.element = el("section", { class: "gallery-editor" }, [
      el("div", { class: "gallery-editor-heading" }, [
        el("div", {}, [
          el("h3", { text: "Article gallery" }),
          el("p", {
            class: "muted",
            text: "Attached images appear at the bottom. Choose one as the profile picture.",
          }),
        ]),
        el("button", {
          type: "button",
          class: "btn sm secondary",
          text: "＋ Add image",
          onclick: () => this.onChoose?.(),
        }),
      ]),
      this.list,
    ]);
    this._render();
  }

  attach(mediaId, suggestedCaption = "") {
    if (!this.items.some((item) => item.media_id === mediaId)) {
      this.items.push({ media_id: mediaId, caption: String(suggestedCaption || "") });
      this._render();
    }
  }

  value() {
    return {
      gallery: this.items.map((item) => ({ ...item })),
      profileImage: this.profileImage,
    };
  }

  _render() {
    clear(this.list);
    if (!this.items.length) {
      this.list.appendChild(el("p", {
        class: "muted gallery-editor-empty",
        text: "No images are attached to this article.",
      }));
      return;
    }
    this.items.forEach((item, index) => this.list.appendChild(this._row(item, index)));
  }

  _row(item, index) {
    const preview = el("div", { class: "gallery-editor-preview" }, [
      el("span", { class: "image-placeholder", text: "Loading…" }),
    ]);
    resolveMedia(this.db, item.media_id).then((media) => {
      clear(preview);
      preview.appendChild(el("img", { src: media.thumbnail_url, alt: media.alt, loading: "lazy" }));
    }).catch(() => {
      preview.textContent = "Unavailable";
      preview.classList.add("image-missing");
    });

    const caption = el("input", {
      type: "text",
      value: item.caption,
      placeholder: "Gallery caption (optional)",
      "aria-label": "Gallery caption",
      oninput: (event) => { item.caption = event.currentTarget.value; },
    });
    const selected = item.media_id === this.profileImage;
    return el("div", { class: `gallery-editor-row${selected ? " is-profile" : ""}` }, [
      preview,
      el("div", { class: "gallery-editor-fields" }, [
        caption,
        el("span", {
          class: "muted gallery-editor-id",
          text: selected ? "Profile picture" : item.media_id,
        }),
      ]),
      el("div", { class: "gallery-editor-actions" }, [
        el("button", {
          type: "button", class: "btn sm secondary", text: "↑", title: "Move up",
          disabled: index === 0 ? "disabled" : null,
          onclick: () => this._move(index, -1),
        }),
        el("button", {
          type: "button", class: "btn sm secondary", text: "↓", title: "Move down",
          disabled: index === this.items.length - 1 ? "disabled" : null,
          onclick: () => this._move(index, 1),
        }),
        el("button", {
          type: "button", class: "btn sm secondary",
          text: selected ? "Remove profile" : "Use as profile",
          onclick: () => {
            this.profileImage = selected ? null : item.media_id;
            this._render();
          },
        }),
        el("button", {
          type: "button", class: "btn sm danger", text: "Detach",
          onclick: () => this._detach(index),
        }),
      ]),
    ]);
  }

  _move(index, offset) {
    const [item] = this.items.splice(index, 1);
    this.items.splice(index + offset, 0, item);
    this._render();
  }

  _detach(index) {
    if (this.canDetach && !this.canDetach(this.items[index].media_id)) {
      toast("Remove this image from the article body before detaching it.", true);
      return;
    }
    const [removed] = this.items.splice(index, 1);
    if (removed.media_id === this.profileImage) this.profileImage = null;
    this._render();
  }
}
