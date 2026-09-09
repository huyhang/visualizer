// The World Gallery: everything a world holds, and the controls for looking
// after it.
//
// Uploading happens inside an article, because an upload is made *for* one and
// needs write access to it. Everything afterwards is a property of the world,
// not of whichever article you happened to be editing — what is in the library,
// how big it is, what nothing points at any more, and what should go. Those
// belong on a page of the world's own, which is what this is.
//
// The unused marks come from `?orphans=1`, which counts retained revisions as
// references. So "unused" here means the same thing it means to the delete
// guard: this will go without an argument.

import { api } from "./api.js";
import { clear, el, toast } from "./dom.js";
import {
  assetNoun, assetPreview, deleteAsset, openImageLightbox, rememberMedia,
} from "./media.js";
import { T } from "./terms.js";
import { crumbs, timeAgo } from "./views.js";

export async function mountWorldGallery(container, database, handlers) {
  new WorldGallery(container, database, handlers).mount();
}

function bytes(count) {
  if (!count) return "—";
  if (count < 1024) return `${count} B`;
  if (count < 1024 * 1024) return `${(count / 1024).toFixed(0)} KB`;
  return `${(count / (1024 * 1024)).toFixed(1)} MB`;
}

function sizeOf(item) {
  // Distinct blobs only: a declined derivative shares the original's bytes, and
  // counting it twice would overstate what the world costs.
  const seen = new Map();
  for (const variant of Object.values(item.variants || {})) {
    if (variant.sha256) seen.set(variant.sha256, variant.bytes || 0);
  }
  return [...seen.values()].reduce((total, n) => total + n, 0);
}

class WorldGallery {
  constructor(container, database, handlers) {
    this.container = container;
    this.database = database;
    this.handlers = handlers;
    this.items = [];
    this.orphans = new Set();
    this.selected = null;
    this.unusedOnly = false;
  }

  async mount() {
    clear(this.container);
    this.crumbBar = el("div", {});
    this.heading = el("h1", { class: "view-title", text: "World Gallery" });
    this.lead = el("p", { class: "view-lead muted", text: "Loading…" });
    this.filter = el("label", { class: "gallery-filter", hidden: "hidden" }, []);
    this.grid = el("div", { class: "world-gallery-grid" });
    this.detail = el("aside", { class: "world-gallery-detail", hidden: "hidden" });

    this._showCrumbs(this.database);
    this.container.appendChild(el("div", { class: "view" }, [
      this.crumbBar,
      el("div", { class: "view-head" }, [
        this.heading,
        el("div", { class: "view-actions" }, [
          el("button", {
            class: "btn sm secondary", type: "button",
            text: `Back to ${T.database.one}`,
            onclick: () => this.handlers.onDatabase(this.database),
          }),
        ]),
      ]),
      this.lead,
      this.filter,
      el("div", { class: "world-gallery-body" }, [this.grid, this.detail]),
    ]));

    await this._load();
  }

  _showCrumbs(title) {
    clear(this.crumbBar);
    this.crumbBar.appendChild(crumbs([
      { label: "Home", onClick: this.handlers.onHome },
      { label: title, onClick: () => this.handlers.onDatabase(this.database) },
      { label: "Gallery" },
    ]));
  }

  async _load() {
    try {
      const body = await api.listMedia(this.database, { orphans: true });
      this.items = body.media;
      this.orphans = new Set(body.orphans || []);
    } catch (error) {
      this.lead.textContent =
        error.message || "Could not load this world's library.";
      return;
    }
    this.items.forEach(rememberMedia);
    this._paintLead();
    this._paintFilter();
    this._paint();
  }

  _paintLead() {
    if (!this.items.length) {
      this.lead.textContent =
        `Nothing here yet. Images and dioramas are added while editing an `
        + `${T.document.one}, and appear here afterwards.`;
      return;
    }
    const total = this.items.reduce((sum, item) => sum + sizeOf(item), 0);
    const dioramas = this.items.filter((i) => i.kind === "diorama").length;
    const kinds = [
      `${this.items.length - dioramas} image${this.items.length - dioramas === 1 ? "" : "s"}`,
      dioramas ? `${dioramas} diorama${dioramas === 1 ? "" : "s"}` : null,
    ].filter(Boolean).join(" · ");
    const unused = this.orphans.size
      ? ` · ${this.orphans.size} unused`
      : "";
    this.lead.textContent = `${kinds} · ${bytes(total)}${unused}`;
  }

  _paintFilter() {
    clear(this.filter);
    if (!this.orphans.size) {
      this.filter.hidden = true;
      return;
    }
    this.filter.hidden = false;
    const box = el("input", { type: "checkbox" });
    box.checked = this.unusedOnly;
    box.addEventListener("change", () => {
      this.unusedOnly = box.checked;
      this._paint();
    });
    this.filter.appendChild(box);
    this.filter.appendChild(el("span", {
      text: ` Show only what nothing points at (${this.orphans.size})`,
    }));
  }

  _shown() {
    return this.unusedOnly
      ? this.items.filter((item) => this.orphans.has(item.id))
      : this.items;
  }

  _paint() {
    clear(this.grid);
    const shown = this._shown();
    if (!shown.length) {
      this.grid.appendChild(el("p", { class: "empty", text:
        this.items.length ? "Everything here is in use." : "Nothing to show." }));
      this._clearDetail();
      return;
    }
    shown.forEach((item) => this.grid.appendChild(this._card(item)));
    const still = shown.find((item) => item.id === this.selected);
    if (still) this._showDetail(still);
    else this._clearDetail();
  }

  _card(item) {
    const selected = item.id === this.selected;
    return el("button", {
      type: "button",
      class: `world-gallery-card${selected ? " selected" : ""}`
           + `${item.kind === "diorama" ? " is-diorama" : ""}`,
      "aria-pressed": selected ? "true" : "false",
      onclick: () => { this.selected = item.id; this._paint(); },
    }, [
      assetPreview(item),
      el("span", { class: "world-gallery-name", text: item.alt || item.filename }),
      el("span", { class: "world-gallery-meta", text: bytes(sizeOf(item)) }),
      this.orphans.has(item.id)
        ? el("span", { class: "world-gallery-unused", text: "unused" })
        : null,
    ]);
  }

  _clearDetail() {
    clear(this.detail);
    this.detail.hidden = true;
  }

  _showDetail(item) {
    clear(this.detail);
    this.detail.hidden = false;
    const noun = assetNoun(item);
    const measure = item.kind === "diorama"
      ? `${(item.model?.vertices || 0).toLocaleString()} vertices · `
        + `${item.model?.textures || 0} textures`
      : `${item.width}×${item.height} · ${item.format}`;

    const alt = el("input", { type: "text", value: item.alt, maxlength: "300" });
    alt.disabled = !item.can_manage;

    const actions = [];
    if (item.can_manage) {
      actions.push(el("button", {
        class: "btn sm secondary", type: "button", text: "Save alt text",
        onclick: () => this._saveAlt(item, alt.value),
      }));
    }
    if (item.can_manage && item.kind === "diorama") {
      actions.push(el("button", {
        class: "btn sm secondary", type: "button", text: "Adjust camera & lights",
        onclick: () => this._adjust(item),
      }));
    }
    actions.push(el("button", {
      class: "btn sm secondary", type: "button", text: "Open full size",
      onclick: () => openImageLightbox(item, ""),
    }));
    if (item.can_manage) {
      actions.push(el("button", {
        class: "btn sm danger", type: "button", text: `Delete ${noun}`,
        onclick: () => this._delete(item),
      }));
    }

    this.detail.appendChild(el("div", { class: "world-gallery-detail-inner" }, [
      el("h2", { class: "section-title", text: item.filename }),
      el("dl", { class: "world-gallery-facts" }, [
        el("dt", { text: "Kind" }), el("dd", { text: noun }),
        el("dt", { text: "Size" }), el("dd", { text: `${measure} · ${bytes(sizeOf(item))}` }),
        el("dt", { text: "Added" }), el("dd", { text: timeAgo(item.created_at) }),
        el("dt", { text: "By" }), el("dd", { text: item.uploader }),
        el("dt", { text: "In use" }),
        el("dd", {
          text: this.orphans.has(item.id)
            ? "Nothing points at this — deleting it will not break an article."
            : "Shown by at least one article, or by a retained revision of one.",
        }),
      ]),
      el("div", { class: "field" }, [
        el("label", { text: "Alternative text" }),
        alt,
        el("small", { class: "muted field-help", text:
          "Describes it for anyone who cannot see it." }),
      ]),
      el("div", { class: "world-gallery-actions" }, actions),
      item.can_manage ? null : el("p", { class: "muted field-help", text:
        `Only ${item.uploader} or this ${T.database.one}'s owner can change this.` }),
    ]));
  }

  async _saveAlt(item, value) {
    if (!value.trim()) { toast("Alternative text cannot be empty.", true); return; }
    try {
      const updated = await api.updateMedia(this.database, item.id, value);
      rememberMedia(updated);
      this.items = this.items.map((e) => (e.id === updated.id ? updated : e));
      this._paint();
      toast("Alternative text saved.");
    } catch (error) {
      toast(error.message || "Could not save that.", true);
    }
  }

  async _adjust(item) {
    const { openDioramaEditor } = await import("./diorama-form.js");
    openDioramaEditor({ db: this.database }, item, {
      onSaved: (updated) => {
        rememberMedia(updated);
        this.items = this.items.map((e) => (e.id === updated.id ? updated : e));
        this._paint();
      },
    });
  }

  async _delete(item) {
    await deleteAsset(this.database, item, {
      // Reload rather than splice: deleting one thing can make another an
      // orphan, and a stale "unused" count is worse than a second request.
      onDeleted: () => { this.selected = null; this._load(); },
    });
  }
}
