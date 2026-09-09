// Media-library UI and the small pieces of image-directive editing around it.

import { api } from "./api.js";
import { clear, el, modal, toast } from "./dom.js";
import { formatImageDirective, parseImageDirective } from "./image-format.js";

export { formatImageDirective } from "./image-format.js";

const mediaCache = new Map();

export async function resolveMedia(db, id) {
  const key = `${db}/${id}`;
  if (!mediaCache.has(key)) {
    mediaCache.set(key, api.getMedia(db, id).catch((error) => {
      mediaCache.delete(key);
      throw error;
    }));
  }
  return mediaCache.get(key);
}

export function rememberMedia(media) {
  mediaCache.set(`${media.world}/${media.id}`, Promise.resolve(media));
}

export function directiveAtCursor(area) {
  const start = area.value.lastIndexOf("\n", Math.max(0, area.selectionStart - 1)) + 1;
  const next = area.value.indexOf("\n", area.selectionStart);
  const end = next === -1 ? area.value.length : next;
  const placement = parseImageDirective(area.value.slice(start, end));
  return placement ? { start, end, placement } : null;
}

export function insertImageDirective(area, placement, existing = null) {
  const directive = formatImageDirective(placement);
  const start = existing ? existing.start : area.selectionStart;
  const end = existing ? existing.end : area.selectionEnd;
  const before = area.value.slice(0, start);
  const after = area.value.slice(end);
  const prefix = before && !before.endsWith("\n") ? "\n" : "";
  const suffix = after && !after.startsWith("\n") ? "\n" : "";
  area.value = before + prefix + directive + suffix + after;
  const cursor = before.length + prefix.length + directive.length;
  area.focus();
  area.setSelectionRange(cursor, cursor);
  area.dispatchEvent(new Event("input"));
}

export function openImageLibrary(area, scope, { beforeUpload, onAttach, attachOnly = false } = {}) {
  new MediaLibraryDialog(area, scope, beforeUpload, onAttach, attachOnly).open();
}

class MediaLibraryDialog {
  constructor(area, scope, beforeUpload, onAttach, attachOnly) {
    this.area = area;
    this.scope = scope;
    this.beforeUpload = beforeUpload;
    this.onAttach = onAttach;
    this.attachOnly = attachOnly;
    this.existing = area ? directiveAtCursor(area) : null;
    this.selected = this.existing?.placement.media_id || null;
    this.items = [];
    this._makeControls();
  }

  open() {
    modal({
      title: this.attachOnly ? "Add gallery image" : (this.existing ? "Edit image" : "Insert image"),
      body: this._body(),
      actions: [
        { label: "Cancel", variant: "secondary" },
        {
          label: this.attachOnly ? "Attach" : (this.existing ? "Apply" : "Insert"),
          onClick: (close) => this._apply(close),
        },
      ],
    });
    this._load();
  }

  _makeControls() {
    this.grid = el("div", { class: "media-grid" });
    this.file = el("input", { type: "file", accept: "image/jpeg,image/png,image/webp" });
    this.uploadAlt = el("input", { type: "text", placeholder: "Describe the image" });
    this.uploadStatus = el("span", { class: "muted media-upload-status" });
    this.caption = el("input", { type: "text", placeholder: "Caption (optional)" });
    this.caption.value = this.existing?.placement.caption || "";
    this.align = this._alignmentControl();
    this.width = el("input", { type: "range", min: "10", max: "100", step: "5" });
    this.width.value = this.existing?.placement.width || 60;
    this.widthValue = el("span", { class: "media-width-value" });
    this.manageAlt = el("input", { type: "text", placeholder: "Alternative text" });
    this.manageStatus = el("span", { class: "muted media-upload-status" });
    this.saveAlt = el("button", { type: "button", class: "btn sm secondary", text: "Save alt text" });
    this.remove = el("button", { type: "button", class: "btn sm danger", text: "Delete image" });
    this.manage = this._manageSection();
    this._wireControls();
  }

  _alignmentControl() {
    const control = el("select", {}, ["left", "center", "right", "full"].map((value) =>
      el("option", { value, text: value[0].toUpperCase() + value.slice(1) })));
    control.value = this.existing?.placement.align || "center";
    return control;
  }

  _wireControls() {
    this.width.addEventListener("input", () => this._showWidth());
    this.align.addEventListener("change", () => this._showWidth());
    this.saveAlt.addEventListener("click", () => this._saveAlt());
    this.remove.addEventListener("click", () => this._delete());
    this._showWidth();
  }

  _showWidth() {
    this.width.disabled = this.align.value === "full";
    this.widthValue.textContent = this.width.disabled ? "100%" : `${this.width.value}%`;
  }

  _body() {
    return el("div", { class: "media-dialog" }, [
      this._uploadSection(),
      el("h3", { text: "Choose from this world" }),
      this.grid,
      this.manage,
      this._placementSection(),
    ]);
  }

  _uploadSection() {
    const button = el("button", {
      type: "button", class: "btn sm secondary", text: "Upload",
      onclick: () => this._upload(button),
    });
    return el("section", { class: "media-upload" }, [
      el("h3", { text: "Upload a new image" }),
      el("div", { class: "field" }, [el("label", { text: "JPEG, PNG, or WebP" }), this.file]),
      el("div", { class: "field" }, [el("label", { text: "Alternative text" }), this.uploadAlt]),
      el("div", { class: "media-upload-action" }, [button, this.uploadStatus]),
    ]);
  }

  _manageSection() {
    return el("section", { class: "media-manage", hidden: "hidden" }, [
      el("h3", { text: "Selected image" }),
      el("div", { class: "field" }, [el("label", { text: "Alternative text" }), this.manageAlt]),
      el("div", { class: "media-upload-action" }, [this.saveAlt, this.remove, this.manageStatus]),
    ]);
  }

  _placementSection() {
    return el("section", { class: "media-placement", hidden: this.attachOnly ? "hidden" : null }, [
      el("div", { class: "field" }, [el("label", { text: "Caption" }), this.caption]),
      el("div", { class: "media-placement-row" }, [
        el("div", { class: "field" }, [el("label", { text: "Alignment" }), this.align]),
        el("div", { class: "field media-width" }, [el("label", { text: "Width" }), this.width, this.widthValue]),
      ]),
    ]);
  }

  async _load() {
    try {
      this.items = (await api.listMedia(this.scope.db)).media;
      this._paint();
    } catch (error) {
      clear(this.grid);
      this.grid.appendChild(el("p", {
        class: "form-error", text: error.message || "Could not load images.",
      }));
    }
  }

  _paint() {
    clear(this.grid);
    this.manage.hidden = true;
    if (!this.items.length) {
      this.grid.appendChild(el("p", { class: "muted", text: "No images are available yet." }));
      return;
    }
    this.items.forEach((item) => this.grid.appendChild(this._card(item)));
    const selected = this.items.find((item) => item.id === this.selected);
    if (selected) this._showManaged(selected);
  }

  _card(item) {
    rememberMedia(item);
    const card = el("button", {
      type: "button",
      class: `media-card${item.id === this.selected ? " selected" : ""}`,
      onclick: () => this._select(item, card),
    }, [
      el("img", { src: item.thumbnail_url, alt: "", loading: "lazy" }),
      el("span", { text: item.alt }),
    ]);
    return card;
  }

  _select(item, card) {
    this.selected = item.id;
    for (const node of this.grid.querySelectorAll(".media-card")) node.classList.remove("selected");
    card.classList.add("selected");
    this._showManaged(item);
  }

  _showManaged(item) {
    this.manage.hidden = false;
    this.manageAlt.value = item.alt;
    this.manageAlt.disabled = !item.can_manage;
    this.saveAlt.hidden = !item.can_manage;
    this.remove.hidden = !item.can_manage;
    this.manageStatus.textContent = `${item.filename} · uploaded by ${item.uploader}`;
  }

  async _upload(button) {
    if (!this.file.files?.length || !this.uploadAlt.value.trim()) {
      this.uploadStatus.textContent = "Choose a file and add alternative text.";
      return;
    }
    button.disabled = true;
    this.uploadStatus.textContent = "Uploading…";
    try {
      if (this.beforeUpload) await this.beforeUpload();
      const uploaded = await api.uploadMedia(
        this.scope.db, this.scope.col, this.scope.id,
        this.file.files[0], this.uploadAlt.value,
      );
      rememberMedia(uploaded);
      if (this.onAttach) this.onAttach(uploaded.id, this.caption.value);
      this.selected = uploaded.id;
      this.file.value = "";
      this.uploadAlt.value = "";
      this.uploadStatus.textContent = "Uploaded.";
      await this._load();
    } catch (error) {
      this.uploadStatus.textContent = error.message || "Upload failed.";
    } finally {
      button.disabled = false;
    }
  }

  async _saveAlt() {
    if (!this.selected || !this.manageAlt.value.trim()) return;
    try {
      const updated = await api.updateMedia(
        this.scope.db, this.selected, this.manageAlt.value,
      );
      rememberMedia(updated);
      this.items = this.items.map((item) => item.id === this.selected ? updated : item);
      this._paint();
      toast("Alternative text saved.");
    } catch (error) { toast(error.message || "Could not update the image.", true); }
  }

  async _delete(force = false) {
    if (!this.selected) return false;
    try {
      await api.deleteMedia(this.scope.db, this.selected, force);
      mediaCache.delete(`${this.scope.db}/${this.selected}`);
      this.items = this.items.filter((item) => item.id !== this.selected);
      this.selected = null;
      this._paint();
      toast("Image deleted.");
      return true;
    } catch (error) {
      if (error.status === 409 && !force) this._confirmForceDelete(error.body?.references || []);
      else toast(error.message || "Could not delete the image.", true);
      return false;
    }
  }

  _confirmForceDelete(references) {
    const explanation = references.length
      ? "Deleting it will leave a placeholder in these article versions:"
      : "This image is used by an article version you cannot view. Deleting it will leave a placeholder there.";
    const list = references.length ? el("ul", {}, references.slice(0, 8).map((ref) => el("li", {
      text: `${ref.collection} / ${ref.article}, revision ${ref.revision}${ref.current ? " (current)" : ""}`,
    }))) : null;
    modal({
      title: "Delete an image that is still used?",
      body: el("div", {}, [el("p", { text: explanation }), list]),
      actions: [
        { label: "Keep image", variant: "secondary" },
        { label: "Force delete", variant: "danger", onClick: async (close) => {
            if (await this._delete(true)) close();
          } },
      ],
    });
  }

  _apply(close) {
    if (!this.selected) { toast("Choose or upload an image first.", true); return; }
    if (!this.attachOnly) {
      insertImageDirective(this.area, {
        id: this.selected,
        align: this.align.value,
        width: this.align.value === "full" ? 100 : this.width.value,
        caption: this.caption.value,
      }, this.existing);
    }
    if (this.onAttach) this.onAttach(this.selected, this.caption.value);
    close();
  }
}

export function openImageLightbox(media, caption) {
  const image = el("img", {
    src: media.original_url,
    alt: media.alt,
    class: "lightbox-image",
    title: "Click to toggle actual size",
    onclick: (event) => event.currentTarget.classList.toggle("actual-size"),
  });
  const figure = el("figure", { class: "lightbox-figure" }, [
    image,
    caption ? el("figcaption", { text: caption }) : null,
  ]);
  modal({
    title: media.filename,
    body: figure,
    actions: [{ label: "Close", variant: "secondary" }],
    className: "image-lightbox",
  });
}
