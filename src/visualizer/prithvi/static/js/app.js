// The map browser: worlds -> that world's maps -> one map with its pins.
//
// This module is the only stateful one. It owns `state`, decides what the page
// should look like, and hands the drawing to `mapview` and the article card to
// `preview`. Everything it needs to *calculate* -- what the zoom box is, what
// the unsaved diff is, where a click landed -- lives in a pure module beside it.

import { api, ApiError } from "./api.js";
import {
  changeCount, clonePins, movePin, pinChanges, pinKey, placePin, removePin, samePin,
} from "./draft.js";
import { mountMap } from "./mapview.js";
import { clearPreview, showPreview, showUnavailable } from "./preview.js";
import { slugify } from "./shared/slug.js";
import {
  anchoredScroll, clampZoom, fitBox, MAX_ZOOM, MIN_ZOOM, scrollRatio, zoomFromWheel,
  ZOOM_STEP,
} from "./zoom.js";

const $ = (id) => document.getElementById(id);

const el = {
  worldsView: $("worlds-view"),
  mapsView: $("maps-view"),
  mapView: $("map-view"),
  worldGrid: $("world-grid"),
  worldsEmpty: $("worlds-empty"),
  mapGrid: $("map-grid"),
  mapsEmpty: $("maps-empty"),
  worldTitle: $("world-title"),
  worldLead: $("world-lead"),
  worldCrumb: $("world-crumb"),
  homeLinks: document.querySelectorAll(".to-worlds"),
  mapWorldLink: $("map-world-link"),
  mapCrumb: $("map-crumb"),
  uploadForm: $("upload-form"),
  mapFile: $("map-file"),
  mapName: $("map-name"),
  mapTitle: $("map-title"),
  mapMeta: $("map-meta"),
  mapStage: $("map-stage"),
  deleteMap: $("delete-map"),
  notice: $("notice"),
  picker: $("picker"),
  search: $("article-search"),
  results: $("article-results"),
  placing: $("placing"),
  placingName: $("placing-name"),
  cancelPlacing: $("cancel-placing"),
  editBar: $("edit-bar"),
  dirty: $("dirty-state"),
  discard: $("discard-changes"),
  save: $("save-changes"),
  zoomOut: $("zoom-out"),
  zoomReset: $("zoom-reset"),
  zoomIn: $("zoom-in"),
};

const preview = {
  panel: $("pin-preview"),
  empty: $("inspector-empty"),
  eyebrow: $("preview-eyebrow"),
  title: $("preview-title"),
  excerpt: $("preview-excerpt"),
  facts: $("preview-facts"),
  link: $("preview-link"),
  remove: $("remove-pin"),
};

const state = {
  worlds: [], world: null, maps: [], map: null,
  svg: "", savedPins: [], pins: [],
  fit: { width: 0, height: 0 }, zoom: 1,
  picking: null, selected: null, saving: false,
  hash: "#/", restoring: false, searchTimer: null,
};

// -- routing -------------------------------------------------------------------

function parseHash() {
  return location.hash.replace(/^#\/?/, "").split("/").filter(Boolean)
    .map(decodeURIComponent);
}

const goWorlds = () => { location.hash = "#/"; };
const goWorld = (world) => { location.hash = `#/${encodeURIComponent(world)}`; };
const goMap = (world, map) => {
  location.hash = `#/${encodeURIComponent(world)}/${encodeURIComponent(map)}`;
};

async function route() {
  const [worldId, mapId] = parseHash();
  if (!worldId) return showWorlds();
  const world = state.worlds.find((candidate) => candidate.id === worldId);
  // A world that is not in the catalog is one this reader cannot open; sending
  // them home is honest and avoids a request we know would be refused.
  if (!world) return goWorlds();
  await openWorld(world);
  if (mapId) await openMap(mapId);
  return undefined;
}

async function onHashChange() {
  if (state.restoring) {
    state.restoring = false;
    return;
  }
  if (hasChanges() && !confirm("Leave this map and discard your unsaved changes?")) {
    state.restoring = true;
    location.hash = state.hash;
    return;
  }
  await guard(async () => {
    await route();
    state.hash = location.hash || "#/";
  });
}

function showView(name) {
  el.worldsView.hidden = name !== "worlds";
  el.mapsView.hidden = name !== "maps";
  el.mapView.hidden = name !== "map";
}

// -- worlds and maps -------------------------------------------------------------

function showWorlds() {
  state.world = null;
  state.map = null;
  renderWorlds();
  showView("worlds");
}

function renderWorlds() {
  el.worldGrid.replaceChildren(...state.worlds.map((world) => card({
    title: world.title,
    subtitle: world.title === world.id ? "" : world.id,
    meta: count(world.map_count, "map"),
    onClick: () => goWorld(world.id),
  })));
  el.worldsEmpty.hidden = state.worlds.length > 0;
}

async function openWorld(world) {
  state.world = world;
  state.map = null;
  state.savedPins = [];
  state.pins = [];
  cancelPlacing();
  clearPreview(preview);
  const page = await api.maps(world.id);
  state.maps = page.maps.sort(byTitle);
  el.worldTitle.textContent = world.title;
  el.worldCrumb.textContent = world.title;
  el.worldLead.textContent = `${count(state.maps.length, "map")} in this world.`;
  // The upload form is the world's `write` grant, made visible.
  el.uploadForm.hidden = !world.can_write;
  renderMaps();
  showView("maps");
}

function renderMaps() {
  el.mapGrid.replaceChildren(...state.maps.map((map) => card({
    title: map.title,
    subtitle: map.title === map.id ? "" : map.id,
    meta: `${map.view_box[2]} × ${map.view_box[3]}`,
    onClick: () => goMap(state.world.id, map.id),
  })));
  el.mapsEmpty.hidden = state.maps.length > 0;
}

function card({ title, subtitle, meta, onClick }) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "card";
  button.append(span("card-title", title));
  if (subtitle) button.append(span("card-sub", subtitle));
  button.append(span("card-meta", meta));
  button.addEventListener("click", onClick);
  return button;
}

function span(className, text) {
  const node = document.createElement("span");
  node.className = className;
  node.textContent = text;
  return node;
}

// -- one map ---------------------------------------------------------------------

async function openMap(mapId) {
  const known = state.maps.find((map) => map.id === mapId);
  if (!known) return goWorld(state.world.id);
  cancelPlacing();
  state.selected = null;
  state.zoom = 1;
  clearPreview(preview);
  const [map, svg, page] = await Promise.all([
    api.map(state.world.id, mapId),
    api.svg(state.world.id, mapId),
    api.pins(state.world.id, mapId),
  ]);
  state.map = map;
  state.svg = svg;
  state.savedPins = clonePins(page.pins);
  state.pins = clonePins(page.pins);
  el.picker.hidden = !state.world.can_write;
  el.editBar.hidden = !state.world.can_write;
  el.deleteMap.hidden = !state.world.can_delete;
  el.mapWorldLink.textContent = state.world.title;
  el.mapCrumb.textContent = map.title;
  el.mapTitle.textContent = map.title;
  showView("map");
  // Measured only once the view is on screen: a hidden stage has no size, and
  // fitting to zero would make the drawing vanish.
  measureFit();
  updateMeta();
  updateEditBar();
  updateZoom();
  renderMap();
  if (state.world.can_write) await searchArticles();
  return undefined;
}

// The viewport, and the drawing's size at 100% within it. Read from the stage's
// *layout* box, which the CSS pins to the grid row, so it is the size of the
// hole the map goes in and never the size of the map already in it.
function measureFit() {
  const rect = el.mapStage.getBoundingClientRect();
  state.fit = fitBox({ width: rect.width, height: rect.height }, state.map.view_box);
}

function renderMap() {
  if (!state.map) return;
  try {
    mountMap(el.mapStage, {
      svgText: state.svg,
      viewBox: state.map.view_box,
      fit: state.fit,
      zoom: state.zoom,
      pins: state.pins,
      selectedPin: state.selected,
      canWrite: state.world.can_write && !state.saving,
      placing: state.saving ? null : state.picking,
      onPlace: stagePin,
      onSelect: selectPin,
      onMove: stageMove,
      onZoom: zoomAt,
    });
  } catch (error) {
    report(error);
  }
}

function updateMeta() {
  const readOnly = state.world.can_write ? "" : " · read only";
  el.mapMeta.textContent =
    `${state.map.id} · ${count(state.pins.length, "pin")}${readOnly}`;
}

// -- zoom --------------------------------------------------------------------------

function zoomAt(deltaY, pointer) {
  const bounds = el.mapStage.getBoundingClientRect();
  setZoom(zoomFromWheel(state.zoom, deltaY), {
    x: pointer.x - bounds.left,
    y: pointer.y - bounds.top,
  });
}

function setZoom(next, anchor = null) {
  const stage = el.mapStage;
  const offsetX = anchor ? anchor.x : stage.clientWidth / 2;
  const offsetY = anchor ? anchor.y : stage.clientHeight / 2;
  const ratioX = scrollRatio(stage.scrollLeft, offsetX, stage.scrollWidth);
  const ratioY = scrollRatio(stage.scrollTop, offsetY, stage.scrollHeight);
  state.zoom = clampZoom(next);
  renderMap();
  stage.scrollLeft = anchoredScroll(ratioX, stage.scrollWidth, offsetX);
  stage.scrollTop = anchoredScroll(ratioY, stage.scrollHeight, offsetY);
  updateZoom();
}

function updateZoom() {
  el.zoomReset.textContent = `${Math.round(state.zoom * 100)}%`;
  el.zoomOut.disabled = state.zoom <= MIN_ZOOM;
  el.zoomIn.disabled = state.zoom >= MAX_ZOOM;
}

// Re-fit rather than re-zoom: the viewport changed, the writer's zoom level did
// not. Because `fit` is derived from the viewport each time and never from the
// last drawing, repeated resizes cannot accumulate.
function refit() {
  if (!state.map) return;
  measureFit();
  renderMap();
}

// -- the article picker ------------------------------------------------------------

async function searchArticles() {
  if (!state.world || !state.world.can_write || !state.map) return;
  await guard(async () => {
    const found = await api.articles(state.world.id, el.search.value.trim());
    const pinned = new Set(state.pins.map(pinKey));
    const choices = found.articles.filter(
      (article) => !pinned.has(pinKey({ article })),
    );
    el.results.replaceChildren(...choices.map(articleChoice));
    if (!choices.length) {
      const empty = document.createElement("p");
      empty.className = "muted";
      empty.textContent = "No unpinned articles match.";
      el.results.append(empty);
    }
  });
}

function articleChoice(article) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "choice";
  const name = document.createElement("strong");
  name.textContent = article.title;
  const scope = `${article.collection_title} · ${article.id}`;
  button.append(name, span("choice-scope", scope));
  button.addEventListener("click", () => beginPlacing(article));
  return button;
}

function beginPlacing(article) {
  if (state.saving) return;
  state.picking = article;
  el.placing.hidden = false;
  el.placingName.textContent = article.title;
  renderMap();
}

function cancelPlacing() {
  state.picking = null;
  el.placing.hidden = true;
  el.placingName.textContent = "";
  if (state.map) renderMap();
}

// -- staging pin edits ---------------------------------------------------------------

async function stagePin(position) {
  if (!state.picking || state.saving) return;
  const article = state.picking;
  state.pins = placePin(state.pins, state.savedPins, {
    world: state.world.id, map: state.map.id, article, position,
  });
  cancelPlacing();
  updateMeta();
  updateEditBar();
  await selectPin(state.pins.find((pin) => pinKey(pin) === pinKey({ article })));
  await searchArticles();
  notify("Pin placed in this draft. Save to keep it.");
}

function stageMove(pin, position) {
  if (state.saving) return renderMap();
  state.pins = movePin(state.pins, pin, position);
  state.selected = state.pins.find((candidate) => samePin(candidate, pin)) || null;
  updateEditBar();
  return renderMap();
}

async function selectPin(pin) {
  if (!pin) return;
  state.selected = pin;
  renderMap();
  const name = pin.article.title || pin.article.id;
  const canWrite = Boolean(state.world.can_write);
  if (pin.article.status !== "available") {
    return showUnavailable(preview, name, canWrite);
  }
  try {
    const article = await api.preview(state.world.id, pin.article);
    showPreview(preview, article, canWrite);
  } catch (error) {
    // The article was readable when the pin listing was built and is not now:
    // deleted, or a grant changed underneath us. Either way the card says so
    // rather than staying on the previous pin's text.
    if (!(error instanceof ApiError)) throw error;
    showUnavailable(preview, name, canWrite);
  }
  return undefined;
}

async function removeSelectedPin() {
  const pin = state.selected;
  if (!pin || state.saving) return;
  state.pins = removePin(state.pins, pin);
  state.selected = null;
  clearPreview(preview);
  updateMeta();
  updateEditBar();
  renderMap();
  await searchArticles();
  notify("Pin removed from this draft. Save to keep the change.");
}

// -- save and cancel ---------------------------------------------------------------

function hasChanges() {
  return changeCount(state.savedPins, state.pins) > 0;
}

function updateEditBar() {
  const changes = changeCount(state.savedPins, state.pins);
  el.dirty.textContent = changes
    ? `${count(changes, "unsaved change")}`
    : "No unsaved changes";
  el.dirty.classList.toggle("unsaved", changes > 0);
  el.discard.disabled = changes === 0 || state.saving;
  el.save.disabled = changes === 0 || state.saving;
  el.save.textContent = state.saving ? "Saving…" : "Save";
  el.search.disabled = state.saving;
  preview.remove.disabled = state.saving;
}

async function cancelChanges() {
  if (!hasChanges()) return;
  state.pins = clonePins(state.savedPins);
  state.selected = null;
  cancelPlacing();
  clearPreview(preview);
  updateMeta();
  updateEditBar();
  renderMap();
  await searchArticles();
  notify("Unsaved changes discarded.");
}

async function saveChanges() {
  if (!hasChanges() || state.saving) return;
  const changes = pinChanges(state.savedPins, state.pins);
  state.saving = true;
  updateEditBar();
  renderMap();
  try {
    // Deletes first, so a draft that frees a name and reuses it cannot collide
    // with itself; every one of these carries the revision it was loaded at.
    for (const pin of changes.deleted) await api.deletePin(worldId(), mapId(), pin);
    for (const pin of changes.moved) await api.movePin(worldId(), mapId(), pin);
    for (const pin of changes.created) {
      await api.createPin(worldId(), mapId(), pin.article, pin.position);
    }
    notify("Map saved.");
  } catch (error) {
    report(conflictMessage(error));
  } finally {
    state.saving = false;
    // Reload before re-rendering either way: after a partial failure the draft
    // and the server disagree, and the server is right.
    await guard(reloadPins);
    updateEditBar();
    renderMap();
  }
}

function conflictMessage(error) {
  if (error instanceof ApiError && error.isConflict) {
    return new Error(
      "Someone else changed this map while you were editing. "
      + "The latest saved pins have been reloaded.",
    );
  }
  return error;
}

async function reloadPins() {
  const page = await api.pins(worldId(), mapId());
  state.savedPins = clonePins(page.pins);
  state.pins = clonePins(page.pins);
  state.selected = null;
  clearPreview(preview);
  updateMeta();
  await searchArticles();
}

const worldId = () => state.world.id;
const mapId = () => state.map.id;

// -- map lifecycle -------------------------------------------------------------------

async function uploadMap(event) {
  event.preventDefault();
  const file = el.mapFile.files[0];
  const name = el.mapName.value.trim();
  if (!file || !name || !state.world.can_write) return;
  await guard(async () => {
    const map = await api.uploadMap(state.world.id, name, file);
    state.maps = [...state.maps, map].sort(byTitle);
    state.world.map_count = state.maps.length;
    el.uploadForm.reset();
    renderWorlds();
    renderMaps();
    goMap(state.world.id, map.id);
    notify(sanitizedMessage(map.sanitization));
  });
}

function sanitizedMessage(report) {
  const removed = Object.values(report?.removed_elements || {})
    .concat(Object.values(report?.removed_attributes || {}))
    .reduce((total, n) => total + n, 0);
  return removed
    ? `Map uploaded; ${count(removed, "unsafe item")} removed from the drawing.`
    : "Map uploaded.";
}

async function deleteCurrentMap() {
  const map = state.map;
  if (!map || !state.world.can_delete) return;
  if (!confirm(`Delete the map "${map.title}" and all of its pins?`)) return;
  await guard(async () => {
    await api.deleteMap(state.world.id, map.id, map.rev);
    state.maps = state.maps.filter((candidate) => candidate.id !== map.id);
    state.world.map_count = state.maps.length;
    state.savedPins = [];
    state.pins = [];
    renderWorlds();
    goWorld(state.world.id);
    notify(`Deleted "${map.title}".`);
  });
}

// -- shell ---------------------------------------------------------------------------

function count(n, noun) {
  return `${n} ${noun}${n === 1 ? "" : "s"}`;
}

function byTitle(left, right) {
  return left.title.localeCompare(right.title);
}

function notify(message, isError = false) {
  el.notice.textContent = message;
  el.notice.classList.toggle("error", isError);
  el.notice.hidden = false;
  clearTimeout(notify.timer);
  notify.timer = setTimeout(() => { el.notice.hidden = true; }, 6000);
}

function report(error) {
  notify(error?.message || "Something went wrong.", true);
}

// Every awaited handler funnels through here so a rejected promise surfaces in
// the notice bar instead of only in the console.
async function guard(work) {
  try {
    await work();
  } catch (error) {
    report(error);
  }
}

function debounce(fn, ms) {
  let timer = null;
  return () => {
    clearTimeout(timer);
    timer = setTimeout(fn, ms);
  };
}

el.homeLinks.forEach((link) => link.addEventListener("click", goWorlds));
el.mapWorldLink.addEventListener("click", () => goWorld(state.world.id));
el.uploadForm.addEventListener("submit", uploadMap);
el.mapFile.addEventListener("change", suggestName);
el.deleteMap.addEventListener("click", deleteCurrentMap);
el.search.addEventListener("focus", searchArticles);
el.search.addEventListener("input", debounce(searchArticles, 180));
el.cancelPlacing.addEventListener("click", cancelPlacing);
preview.remove.addEventListener("click", removeSelectedPin);
el.discard.addEventListener("click", cancelChanges);
el.save.addEventListener("click", saveChanges);
el.zoomOut.addEventListener("click", () => setZoom(state.zoom - ZOOM_STEP));
el.zoomReset.addEventListener("click", () => setZoom(1));
el.zoomIn.addEventListener("click", () => setZoom(state.zoom + ZOOM_STEP));
window.addEventListener("hashchange", onHashChange);
window.addEventListener("resize", debounce(refit, 150));
window.addEventListener("beforeunload", (event) => {
  if (!hasChanges()) return;
  event.preventDefault();
  event.returnValue = "";
});

function suggestName() {
  const file = el.mapFile.files[0];
  if (el.mapName.value || !file) return;
  el.mapName.value = slugify(file.name.replace(/\.svg$/i, ""));
}

// Shared prefs owns both header controls; the map only needs to know when
// the text size changed, because every rem-based dimension just moved.
document.addEventListener("prefs:fontscale", refit);

guard(async () => {
  const found = await api.worlds();
  state.worlds = found.worlds.sort(byTitle);
  renderWorlds();
  await route();
  state.hash = location.hash || "#/";
});
