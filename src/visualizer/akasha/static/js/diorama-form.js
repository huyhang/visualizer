// Adding a diorama: choose a model, aim the camera at it, hang some lanterns.
//
// The controls are controls. The previous round of this feature edited local
// lights as a raw JSON textarea, which asks a writer to know a schema in order
// to put a lamp in a window; here each light is a row of inputs and each field
// says underneath what it does.
//
// The preview is not a courtesy either — it is the thing being uploaded. The
// poster is captured from it at save time, so what the gallery shows is a
// photograph of the scene the writer was looking at, through the camera the
// manifest describes. It cannot drift from the manifest because it is made
// from it.

import { api } from "./api.js";
import { clear, el, modal, toast } from "./dom.js";

const DEFAULTS = {
  camera_azimuth: 35,
  camera_elevation: 25,
  rotation_speed: 6,
  auto_rotate: true,
};

const LIGHT_DEFAULT = {
  type: "point", x: 0, y: 3, z: 0, color: "#ffcc88", intensity: 4,
};

/** Open the add-a-diorama dialog. `onAdded(media)` receives the stored record. */
export function openDioramaDialog(scope, { beforeUpload, onAdded } = {}) {
  new DioramaDialog(scope, { beforeUpload, onAdded }).open();
}

/**
 * Re-aim one that already exists.
 *
 * The same form, with the file input gone: geometry is fixed, and everything
 * else is exactly what it was when the diorama was added. Saving re-shoots the
 * poster as well as storing the numbers — a still taken through the old camera
 * is not a picture of this scene any more.
 */
export function openDioramaEditor(scope, media, { onSaved } = {}) {
  new DioramaDialog(scope, { editing: media, onSaved }).open();
}

class DioramaDialog {
  constructor(scope, { beforeUpload, onAdded, editing = null, onSaved } = {}) {
    this.scope = scope;
    this.beforeUpload = beforeUpload;
    this.onAdded = onAdded;
    this.onSaved = onSaved;
    this.editing = editing;
    this.lights = (editing?.manifest?.lights || []).map((l) => ({ ...l }));
    this.handle = null;
    this.objectUrl = null;
    this._build();
  }

  // -- controls -------------------------------------------------------------

  _build() {
    const existing = { ...DEFAULTS, ...(this.editing?.manifest || {}) };
    this.file = el("input", { type: "file", accept: ".glb,model/gltf-binary" });
    this.file.addEventListener("change", () => this._loadPreview());

    this.title = el("input", { type: "text", placeholder: "Highkeep", maxlength: "120" });
    this.title.value = existing.title || "";
    this.description = el("textarea", {
      rows: "3", maxlength: "1000",
      placeholder: "What a reader is looking at.",
    });
    this.description.value = existing.description || "";
    this.alt = el("input", {
      type: "text", maxlength: "300",
      placeholder: "A mountain fortress of grey stone, lit from the west",
    });
    this.alt.value = this.editing?.alt || "";

    this.azimuth = this._slider("camera_azimuth", 0, 359, 1, existing.camera_azimuth, "°");
    this.elevation = this._slider("camera_elevation", -89, 89, 1, existing.camera_elevation, "°");
    this.speed = this._slider("rotation_speed", 0, 30, 1, existing.rotation_speed, "°/s");
    this.autoRotate = el("input", { type: "checkbox" });
    this.autoRotate.checked = existing.auto_rotate !== false;
    this.autoRotate.addEventListener("change", () => this._reaim());

    this.lightList = el("div", { class: "diorama-lights" });
    this.preview = el("div", { class: "article-diorama diorama-preview" });
    this.previewNote = el("p", {
      class: "muted diorama-note",
      text: "Choose a .glb to see it here. The gallery still is taken from this view.",
    });
    this.status = el("span", { class: "muted media-upload-status" });
    this._paintLights();
  }

  /** A labelled range with a live readout — the value is never a mystery. */
  _slider(name, min, max, step, value, unit) {
    const input = el("input", {
      type: "range", min: String(min), max: String(max), step: String(step),
    });
    input.value = String(value);
    const readout = el("span", { class: "media-width-value", text: `${value}${unit}` });
    input.addEventListener("input", () => {
      readout.textContent = `${input.value}${unit}`;
      this._reaim();
    });
    input.dataset.field = name;
    input.readout = readout;
    return input;
  }

  _field(label, control, help) {
    return el("div", { class: "field" }, [
      el("label", { text: label }),
      control,
      help ? el("small", { class: "muted field-help", text: help }) : null,
    ]);
  }

  _sliderField(label, slider, help) {
    return el("div", { class: "field diorama-slider" }, [
      el("label", { text: label }),
      el("div", { class: "diorama-slider-row" }, [slider, slider.readout]),
      el("small", { class: "muted field-help", text: help }),
    ]);
  }

  // -- local lights ---------------------------------------------------------

  _paintLights() {
    clear(this.lightList);
    if (!this.lights.length) {
      this.lightList.appendChild(el("p", {
        class: "muted",
        text: "No local lights. The scene already has a sun; add lanterns only "
            + "where something should glow.",
      }));
    }
    this.lights.forEach((light, index) => {
      this.lightList.appendChild(this._lightRow(light, index));
    });
    this.lightList.appendChild(el("button", {
      type: "button", class: "btn sm secondary", text: "＋ Add light",
      disabled: this.lights.length >= 8 ? "disabled" : null,
      onclick: () => { this.lights.push({ ...LIGHT_DEFAULT }); this._paintLights(); },
    }));
  }

  _lightRow(light, index) {
    const type = el("select", {}, ["point", "spot"].map((value) =>
      el("option", { value, text: value === "point" ? "Point (a lantern)" : "Spot (a beam)" })));
    type.value = light.type;
    type.addEventListener("change", () => { light.type = type.value; });

    const number = (key, step = "0.5") => {
      const input = el("input", { type: "number", step, value: String(light[key]) });
      input.addEventListener("input", () => { light[key] = Number(input.value) || 0; });
      return input;
    };
    const colour = el("input", { type: "color", value: light.color });
    colour.addEventListener("input", () => { light.color = colour.value; });
    const intensity = el("input", {
      type: "number", min: "0", max: "20", step: "0.5", value: String(light.intensity),
    });
    intensity.addEventListener("input", () => {
      light.intensity = Number(intensity.value) || 0;
    });

    return el("div", { class: "diorama-light-row" }, [
      type,
      el("span", { class: "diorama-xyz" }, [
        el("label", { text: "x" }), number("x"),
        el("label", { text: "y" }), number("y"),
        el("label", { text: "z" }), number("z"),
      ]),
      colour,
      intensity,
      el("button", {
        type: "button", class: "btn sm danger", text: "Remove",
        title: "Remove this light",
        onclick: () => { this.lights.splice(index, 1); this._paintLights(); },
      }),
    ]);
  }

  // -- preview --------------------------------------------------------------

  manifest() {
    return {
      title: this.title.value.trim(),
      description: this.description.value.trim(),
      camera_azimuth: Number(this.azimuth.value),
      camera_elevation: Number(this.elevation.value),
      rotation_speed: Number(this.speed.value),
      auto_rotate: this.autoRotate.checked,
      lights: this.lights.map((light) => ({ ...light })),
    };
  }

  _reaim() {
    this.handle?.stage?.reaim(this.manifest());
  }

  async _loadPreview() {
    this._teardownPreview();
    const chosen = this.file.files?.[0];
    // Editing reads the model already in the library; adding reads the file
    // just chosen. Everything after this point is the same either way.
    if (!chosen && !this.editing) return;
    if (chosen && !this.title.value.trim()) {
      this.title.value = chosen.name.replace(/\.glb$/i, "").replace(/[-_]+/g, " ");
    }
    this.previewNote.textContent = "Building the scene…";
    if (chosen) this.objectUrl = URL.createObjectURL(chosen);
    const { mountDiorama } = await import("./diorama-viewer.js");
    this.handle = mountDiorama(this.preview, {
      modelUrl: this.objectUrl || this.editing.model_url,
      manifest: this.manifest(),
      capture: true,
      eager: true,
      onError: (error) => {
        this.previewNote.textContent = error.message || "That file could not be read.";
      },
    });
    // Lights are baked into the scene when it is built, so changing them
    // rebuilds; the camera sliders only re-aim, which is why they feel live.
    this.previewNote.textContent =
      "Drag to look around. Save takes the gallery still from this view.";
  }

  _teardownPreview() {
    this.handle?.dispose();
    this.handle = null;
    clear(this.preview);
    if (this.objectUrl) URL.revokeObjectURL(this.objectUrl);
    this.objectUrl = null;
  }

  /** Rebuild the scene so newly added lights appear. */
  async _rebuild() {
    if (!this.file.files?.length && !this.editing) {
      toast("Choose a model first.", true);
      return;
    }
    await this._loadPreview();
  }

  // -- dialog ---------------------------------------------------------------

  _body() {
    return el("div", { class: "media-dialog diorama-dialog" }, [
      this.editing
        ? el("p", {
            class: "muted field-help",
            text: `Editing ${this.editing.filename}. The model itself does not `
                + "change — only how it is shown.",
          })
        : el("div", { class: "field" }, [
            el("label", { text: "Model" }),
            this.file,
            el("small", {
              class: "muted field-help",
              text: "A glTF binary (.glb). Everything must be embedded — a "
                  + "model that links out to another server is refused.",
            }),
          ]),
      this._field("Title", this.title, "Shown above the scene when opened full size."),
      this._field("Alternative text", this.alt,
        "Describes the scene for anyone who cannot see it. Required."),
      this._field("Description", this.description,
        "Optional. Shown under the scene in the full-size view."),

      el("h3", { text: "Camera" }),
      this._sliderField("Azimuth", this.azimuth,
        "Which side it is viewed from. Wraps at 360."),
      this._sliderField("Elevation", this.elevation,
        "How far above the ground the camera sits. Level is 0."),
      this._sliderField("Rotation", this.speed,
        "How fast the camera circles. 0 holds it still."),
      el("div", { class: "field diorama-checkbox" }, [
        el("label", {}, [this.autoRotate, el("span", { text: " Turn automatically" })]),
        el("small", {
          class: "muted field-help",
          text: "Ignored for readers who ask for reduced motion.",
        }),
      ]),

      el("h3", { text: "Local lights" }),
      this.lightList,
      el("button", {
        type: "button", class: "btn sm secondary", text: "↻ Rebuild preview",
        onclick: () => this._rebuild(),
        title: "Lights are built into the scene, so adding one rebuilds it",
      }),

      el("h3", { text: "Preview" }),
      this.preview,
      this.previewNote,
      this.status,
    ]);
  }

  open() {
    this.close = modal({
      title: this.editing ? "Adjust this diorama" : "Add a diorama",
      body: this._body(),
      actions: [
        { label: "Cancel", variant: "secondary" },
        {
          label: this.editing ? "Save" : "Upload",
          onClick: (close) => (this.editing ? this._save(close) : this._upload(close)),
        },
      ],
      onClose: () => this._teardownPreview(),
      className: "diorama-modal",
    });
    // Editing has a model already; show it without waiting to be asked.
    if (this.editing) this._loadPreview();
  }

  async _save(close) {
    if (!this.title.value.trim()) { this.status.textContent = "Give it a title."; return; }
    this.status.textContent = "Saving…";
    try {
      // Re-shot from the view being saved. Storing the numbers without the
      // still would leave the gallery showing the camera that was replaced.
      const poster = await this.handle?.stage?.capturePoster();
      const record = await api.updateManifest(
        this.scope.db, this.editing.id, this.manifest(), poster,
      );
      toast("Diorama updated.");
      if (this.onSaved) this.onSaved(record);
      close();
    } catch (error) {
      this.status.textContent = error.message || "The change could not be saved.";
    }
  }

  async _upload(close) {
    const model = this.file.files?.[0];
    if (!model) { this.status.textContent = "Choose a model to upload."; return; }
    if (!this.title.value.trim()) { this.status.textContent = "Give it a title."; return; }
    if (!this.alt.value.trim()) {
      this.status.textContent = "Add alternative text.";
      return;
    }
    this.status.textContent = "Uploading…";
    try {
      if (this.beforeUpload) await this.beforeUpload();
      const poster = await this.handle?.stage?.capturePoster();
      const record = await api.uploadDiorama(
        this.scope.db, this.scope.col, this.scope.id,
        { model, poster, alt: this.alt.value, manifest: this.manifest() },
      );
      toast("Diorama added.");
      if (this.onAdded) this.onAdded(record);
      close();
    } catch (error) {
      this.status.textContent = error.message || "The upload failed.";
    }
  }
}
