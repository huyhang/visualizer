// The interactive shell around timelinelayout.js. Its dependencies are passed
// in: this module owns scrolling and DOM lifetime, not API calls or scene cards.

import { el } from "./dom.js";
import {
  densityBins,
  periodBands,
  ratioForTick,
  scaleFor,
  scrollForTick,
  storyOrder,
  tickAtScroll,
  tickAtRatio,
  visibleBreaks,
  visiblePeriods,
  visibleScenes,
} from "./timelinelayout.js";

const ZOOMS = [0.5, 1, 2, 4, 8];
const LABEL_DELAY = 120;

const clampTick = (bounds, tick) => Math.min(
  bounds.end_tick,
  Math.max(bounds.start_tick, Number(tick)),
);

export function sceneTimeline({
  events = [], unscheduled = [], bounds = null, cursorTick = null, zoom = 1,
  renderScene, formatTick, onCursor = () => {}, onZoom = () => {},
}) {
  const root = el("div", { class: "scene-timeline-root" });
  root.appendChild(unscheduledShelf(unscheduled, renderScene));
  if (!bounds || !events.length) {
    root.prepend(el("p", { class: "empty", text:
      unscheduled.length
        ? "No scheduled scenes match. The undated scenes are collected below."
        : "No scenes match this view." }));
    return { element: root, destroy() {} };
  }

  // Sorted once, not once per frame: `visibleScenes` runs on every scroll frame
  // and the sort is the only part of it that grows with the size of the book.
  const order = storyOrder(events);
  // Where the book's calendar turns over. Derived from the parts the server
  // already sends with each scene, so the rail can band itself by year and
  // month without a second request and without parsing a display string.
  const bands = periodBands(order.ordered);

  let currentZoom = zoom;
  let currentTick = clampTick(bounds, cursorTick == null ? bounds.start_tick : cursorTick);
  let scale = null;
  let frame = null;
  let labelTimer = null;
  let labelVersion = 0;
  let observer = null;
  let touchY = null;
  let destroyed = false;
  const cards = new Map();

  const label = el("span", { class: "scene-cursor-label", text: `Tick ${currentTick}` });
  // The cursor's reading, for a screen reader. Separate from the label above
  // because that one is rewritten on every animation frame, and a live region
  // rewritten sixty times a second is a queue of announcements nobody can
  // listen through. Only the settled tick reaches this one.
  const announcer = el("span", { class: "visually-hidden", "aria-live": "polite" });
  const zoomLabel = el("span", { class: "timeline-zoom-label", text: "100%" });
  const zoomOut = el("button", {
    class: "icon-btn sm", type: "button", text: "−", title: "Show more time",
    "aria-label": "Zoom timeline out", onclick: () => changeZoom(-1),
  });
  const zoomIn = el("button", {
    class: "icon-btn sm", type: "button", text: "+", title: "Show less time",
    "aria-label": "Zoom timeline in", onclick: () => changeZoom(1),
  });
  const beginning = el("button", {
    class: "btn secondary sm", type: "button", text: "Beginning",
    onclick: () => moveTo(bounds.start_tick, true),
  });
  const ending = el("button", {
    class: "btn secondary sm", type: "button", text: "End",
    onclick: () => moveTo(bounds.end_tick, true),
  });
  const toolbar = el("div", { class: "scene-timeline-tools" }, [
    el("span", { class: "muted timeline-count", text:
      `${events.length} scheduled scene${events.length === 1 ? "" : "s"}` }),
    el("div", { class: "timeline-zoom" }, [zoomOut, zoomLabel, zoomIn]),
    beginning,
    ending,
  ]);

  const spacer = el("div", { class: "scene-timeline-spacer" });
  const scroller = el("div", {
    class: "scene-timeline-scroll", tabindex: "0", role: "region",
    "aria-label": "Scene timeline. Scroll to move through time.",
  }, spacer);
  const layer = el("div", { class: "scene-timeline-layer", "aria-live": "off" });
  const cursor = el("div", { class: "scene-time-cursor" }, [
    el("span", { class: "scene-cursor-rule" }), label,
  ]);
  const overview = overviewControl(events, (ratio) => moveTo(tickAtRatio(scale, ratio), false));
  const breakLayer = el("div", { class: "timeline-break-layer", "aria-hidden": "true" });
  const periodLayer = el("div", { class: "timeline-period-layer", "aria-hidden": "true" });
  const stage = el("div", { class: "scene-timeline-stage" }, [
    scroller,
    periodLayer,
    breakLayer,
    layer,
    cursor,
    el("span", { class: "timeline-fade top", "aria-hidden": "true" }),
    el("span", { class: "timeline-fade bottom", "aria-hidden": "true" }),
    overview.element,
  ]);
  root.prepend(toolbar, stage, announcer);

  function rebuildScale() {
    const height = stage.clientHeight || 560;
    scale = scaleFor(bounds, {
      viewportHeight: height, eventCount: events.length, events, zoom: currentZoom,
    });
    spacer.style.height = `${scale.contentHeight}px`;
    zoomLabel.textContent = `${Math.round(scale.zoom * 100)}%`;
    zoomOut.disabled = scale.zoom === ZOOMS[0];
    zoomIn.disabled = scale.zoom === ZOOMS[ZOOMS.length - 1];
    // `behavior: auto` on purpose: the stylesheet asks for smooth scrolling, and
    // under it a plain `scrollTop =` only *starts* an animation — the paint
    // below would then read the old offset and put the cursor back where the
    // zoom just moved it from.
    scroller.scrollTo({ top: scrollForTick(scale, currentTick), behavior: "auto" });
    overview.setScale(scale);
    paint();
  }

  function changeZoom(direction) {
    const at = ZOOMS.indexOf(currentZoom);
    const index = at < 0 ? 1 : at;
    const next = ZOOMS[Math.min(ZOOMS.length - 1, Math.max(0, index + direction))];
    if (next === currentZoom) return;
    currentZoom = next;
    onZoom(next);
    rebuildScale();
  }

  function moveTo(tick, smooth) {
    currentTick = clampTick(bounds, tick);
    scroller.scrollTo({
      top: scrollForTick(scale, currentTick), behavior: smooth ? "smooth" : "auto",
    });
    // A reduced browser shim may not dispatch a scroll for scrollTo; painting
    // here also makes the control respond before smooth motion begins.
    schedulePaint();
  }

  // Direct manipulation tracks the hand, so it overrides the stylesheet's smooth
  // scrolling: animating each wheel notch or touch delta would lag the gesture.
  function nudge(by) {
    scroller.scrollBy({ top: by, behavior: "auto" });
  }

  function schedulePaint() {
    if (frame != null) return;
    frame = requestAnimationFrame(() => {
      frame = null;
      paint();
    });
  }

  function paint() {
    if (!scale) return;
    currentTick = tickAtScroll(scale, scroller.scrollTop);
    onCursor(currentTick);
    overview.update(currentTick, scale);
    label.textContent = `Tick ${currentTick}`;
    scheduleLabel(currentTick);
    paintBreaks();
    paintPeriods();
    paintCards();
  }

  function paintCards() {
    const columns = stage.clientWidth < 720 ? 1 : 2;
    const placements = visibleScenes(order, scale, currentTick, {
      viewportHeight: scale.viewportHeight, columns,
    });
    const displayed = displayPlacements(placements, columns);
    const wanted = new Set(displayed.map((item) => item.key));
    for (const [id, node] of cards) {
      if (!wanted.has(id)) {
        node.remove();
        cards.delete(id);
      }
    }
    for (const item of displayed) {
      let node = cards.get(item.key);
      if (!node) {
        node = item.scenes.length > 1
          ? momentItem(item.scenes, renderScene)
          : sceneItem(item.scenes[0], renderScene);
        cards.set(item.key, node);
        layer.appendChild(node);
      }
      positionItem(node, item.placement, columns);
    }
  }

  function paintBreaks() {
    breakLayer.replaceChildren(...visibleBreaks(scale, currentTick).map((gap) => el("div", {
      class: "timeline-break", style: `top:${gap.y}px`,
    }, [
      el("span", { class: "timeline-break-line" }),
      el("span", { class: "timeline-break-label", text:
        `${gap.rawDuration} ticks later` }),
      el("span", { class: "timeline-break-line" }),
    ])));
  }

  function paintPeriods() {
    periodLayer.replaceChildren(...visiblePeriods(bands, scale, currentTick).map((band) =>
      el("div", {
        class: `timeline-period level-${Math.min(1, band.level)} mark-${band.side}`,
        style: `top:${band.y}px`,
      }, [
        el("span", { class: "timeline-period-rule" }),
        el("span", { class: "timeline-period-label", text: band.labels.join(" · ") }),
      ])));
  }

  function announce(text) {
    if (text && announcer.textContent !== text) announcer.textContent = text;
  }

  function scheduleLabel(tick) {
    clearTimeout(labelTimer);
    const version = ++labelVersion;
    labelTimer = setTimeout(async () => {
      announce(label.textContent);
      try {
        const formatted = await formatTick(tick);
        if (version !== labelVersion || !formatted) return;
        label.textContent = formatted;
        announce(formatted);
      } catch (e) { /* the canonical tick remains visible */ }
    }, LABEL_DELAY);
  }

  function onKey(event) {
    const page = Math.max(80, scale.viewportHeight * 0.72);
    const steps = {
      ArrowUp: -48, ArrowDown: 48, PageUp: -page, PageDown: page,
    };
    if (event.key === "Home") moveTo(bounds.start_tick, false);
    else if (event.key === "End") moveTo(bounds.end_tick, false);
    else if (steps[event.key] != null) scroller.scrollBy({ top: steps[event.key] });
    else return;
    event.preventDefault();
  }

  function forwardWheel(event) {
    if (scroller.contains(event.target)) return;
    if (event.target.closest?.(".timeline-moment-scenes")) return;
    event.preventDefault();
    nudge(event.deltaY);
  }

  function startTouch(event) {
    if (event.target.closest?.(".timeline-moment-scenes")) {
      touchY = null;
      return;
    }
    touchY = event.touches.length === 1 ? event.touches[0].clientY : null;
  }

  function moveTouch(event) {
    if (touchY == null || event.touches.length !== 1) return;
    const next = event.touches[0].clientY;
    nudge(touchY - next);
    touchY = next;
    event.preventDefault();
  }

  function endTouch() { touchY = null; }

  function destroy() {
    if (destroyed) return;
    destroyed = true;
    if (frame != null) window.cancelAnimationFrame(frame);
    clearTimeout(labelTimer);
    observer?.disconnect();
    scroller.removeEventListener("scroll", schedulePaint);
    scroller.removeEventListener("keydown", onKey);
    stage.removeEventListener("wheel", forwardWheel);
    stage.removeEventListener("touchstart", startTouch);
    stage.removeEventListener("touchmove", moveTouch);
    stage.removeEventListener("touchend", endTouch);
  }

  scroller.addEventListener("scroll", schedulePaint, { passive: true });
  scroller.addEventListener("keydown", onKey);
  stage.addEventListener("wheel", forwardWheel, { passive: false });
  stage.addEventListener("touchstart", startTouch, { passive: true });
  stage.addEventListener("touchmove", moveTouch, { passive: false });
  stage.addEventListener("touchend", endTouch, { passive: true });
  if (typeof ResizeObserver === "function") {
    observer = new ResizeObserver(rebuildScale);
    observer.observe(stage);
  }
  requestAnimationFrame(rebuildScale);
  return { element: root, destroy };
}

// The rail furniture every card hangs from, whatever the card is: the span bar,
// the stem down to the anchor, the connector across to the card, and the dot.
function railParts() {
  return ["duration", "stem", "link", "dot"].map((part) => el("span", {
    class: `scene-timeline-${part}`, "aria-hidden": "true",
  }));
}

function timelineItem(dataset, body) {
  return el("div", { class: "scene-timeline-item", dataset }, [
    ...railParts(),
    el("div", { class: "scene-timeline-card" }, body),
  ]);
}

function sceneItem(scene, renderScene) {
  return timelineItem({ event: scene.id }, renderScene(scene, { timeline: true }));
}

function momentItem(scenes, renderScene) {
  const first = scenes[0];
  const names = scenes.slice(0, 3).map((scene) => scene.title).join(" · ");
  const rest = scenes.length > 3 ? ` · +${scenes.length - 3}` : "";
  return timelineItem(
    { moment: String(first.start_tick) },
    el("details", { class: "timeline-moment-card" }, [
      el("summary", {}, [
        el("span", { class: "timeline-moment-count", text:
          `${scenes.length} scenes at ${first.start_label || `tick ${first.start_tick}`}` }),
        el("span", { class: "timeline-moment-names", text: names + rest }),
      ]),
      el("div", { class: "timeline-moment-scenes" },
        scenes.map((scene) => renderScene(scene, { timeline: false }))),
    ]),
  );
}

function displayPlacements(placements, columns) {
  if (columns > 1) {
    return placements.map((placement) => ({
      key: placement.scene.id, placement, scenes: [placement.scene],
    }));
  }
  const grouped = new Map();
  for (const placement of placements) {
    const key = String(placement.scene.start_tick);
    const found = grouped.get(key);
    if (found) found.scenes.push(placement.scene);
    else grouped.set(key, { key: `moment:${key}`, placement, scenes: [placement.scene] });
  }
  return [...grouped.values()].map((item) => item.scenes.length === 1
    ? { ...item, key: item.scenes[0].id }
    : item);
}

function positionItem(node, placement, columns) {
  const cardCenter = 39;
  const anchor = placement.anchorY - placement.top;
  const end = placement.endY - placement.top;
  node.className = `scene-timeline-item side-${columns === 1 ? 1 : placement.side}`;
  node.style.top = `${placement.top}px`;
  node.style.opacity = String(placement.opacity);
  node.style.setProperty("--anchor-y", `${anchor}px`);
  node.style.setProperty("--duration-top", `${Math.min(anchor, end)}px`);
  node.style.setProperty("--duration-height", `${Math.max(3, Math.abs(end - anchor))}px`);
  node.style.setProperty("--stem-top", `${Math.min(anchor, cardCenter)}px`);
  node.style.setProperty("--stem-height", `${Math.max(2, Math.abs(anchor - cardCenter))}px`);
}

function overviewControl(events, onMove) {
  const marks = el("div", { class: "timeline-overview-density", "aria-hidden": "true" });
  const input = el("input", {
    class: "timeline-overview-range", type: "range",
    min: "0", max: "1000", step: "1",
    "aria-label": "Jump to a time on the story overview",
  });
  input.value = "0";
  input.addEventListener("input", () => onMove(Number(input.value) / 1000));
  return {
    element: el("div", { class: "timeline-overview" }, [marks, input]),
    setScale: (scale) => {
      const bins = densityBins(events, scale);
      const peak = Math.max(1, ...bins);
      marks.replaceChildren(...bins.map((amount, index) => amount ? el("span", {
        style: `top:${(index / bins.length) * 100}%;opacity:${0.2 + 0.8 * amount / peak}`,
      }) : null).filter(Boolean));
    },
    update: (tick, scale) => { input.value = String(Math.round(ratioForTick(scale, tick) * 1000)); },
  };
}

function unscheduledShelf(scenes, renderScene) {
  if (!scenes.length) return el("div");
  const body = el("div", { class: "timeline-unscheduled-grid" });
  let built = false;
  const shelf = el("details", { class: "timeline-unscheduled" }, [
    el("summary", { text:
      `${scenes.length} unscheduled scene${scenes.length === 1 ? "" : "s"}` }),
    body,
  ]);
  shelf.addEventListener("toggle", () => {
    if (!shelf.open || built) return;
    built = true;
    for (const scene of scenes) body.appendChild(renderScene(scene, { timeline: false }));
  });
  return shelf;
}
