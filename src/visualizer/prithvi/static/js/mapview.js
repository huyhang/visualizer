// Draws one map: the sanitized SVG, a pin overlay on top of it, and the
// pointer behaviour that makes pins placeable, draggable and selectable.
//
// The element's size comes from `boxForZoom(fit, zoom)` and never from
// measuring the container. See `zoom.js` for why that distinction is the whole
// ballgame; the short version is that measuring the thing you are about to
// resize makes the size compound.

import { clientPoint, insideViewBox } from "./coordinates.js";
import { boxForZoom } from "./zoom.js";

const SVG_NS = "http://www.w3.org/2000/svg";
// Below this much pointer travel a drag is a click that wobbled.
const DRAG_SLOP = 4;
const PIN_RADIUS = 0.014;

export function mountMap(container, {
  svgText, viewBox, fit, zoom, pins, selectedPin, canWrite, placing,
  onPlace, onSelect, onMove, onZoom,
}) {
  const svg = parseSvg(svgText);
  const box = boxForZoom(fit, zoom);
  svg.style.width = `${box.width}px`;
  svg.style.height = `${box.height}px`;
  svg.classList.add("prithvi-map");
  svg.setAttribute("preserveAspectRatio", "xMidYMid meet");
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", "Interactive map");
  container.replaceChildren(svg);
  container.classList.toggle("placing", Boolean(placing));

  // Pins keep a constant size on screen rather than growing with the drawing:
  // you zoom in to read the terrain, not to get bigger markers.
  const radius = (Math.min(viewBox[2], viewBox[3]) * PIN_RADIUS) / zoom;
  const layer = document.createElementNS(SVG_NS, "g");
  layer.setAttribute("class", "pin-layer");
  layer.setAttribute("aria-label", "Map pins");
  for (const pin of pins) {
    layer.appendChild(pinElement(pin, radius, {
      svg, viewBox, canWrite, selected: isSame(pin, selectedPin), onSelect, onMove,
    }));
  }
  svg.appendChild(layer);

  const pan = attachPan(svg, container);
  svg.addEventListener("click", (event) => {
    // A drag that ends over the background is a pan, not a placement. Without
    // this, letting go of the map asks you to pin something.
    if (pan.consumeDrag()) return;
    if (!placing || event.target.closest(".pin")) return;
    const point = clientPoint(svg, event.clientX, event.clientY);
    if (insideViewBox(point, viewBox)) onPlace(point);
  });
  svg.addEventListener("wheel", (event) => {
    event.preventDefault();
    onZoom(event.deltaY, { x: event.clientX, y: event.clientY });
  }, { passive: false });

  return svg;
}

function parseSvg(svgText) {
  const parsed = new DOMParser().parseFromString(svgText, "image/svg+xml");
  if (parsed.querySelector("parsererror")) {
    throw new Error("This map's drawing could not be displayed.");
  }
  return document.importNode(parsed.documentElement, true);
}

// Dragging the background scrolls the stage. Reports whether the gesture that
// just ended travelled far enough to count as a drag, so the click it
// generates can be ignored exactly once.
function attachPan(svg, container) {
  let origin = null;
  let dragged = false;

  svg.addEventListener("pointerdown", (event) => {
    if (event.button !== 0 || event.target.closest(".pin")) return;
    origin = { x: event.clientX, y: event.clientY };
    container.classList.add("panning");
    svg.setPointerCapture(event.pointerId);
  });
  svg.addEventListener("pointermove", (event) => {
    if (!origin) return;
    const dx = event.clientX - origin.x;
    const dy = event.clientY - origin.y;
    if (Math.abs(dx) > DRAG_SLOP || Math.abs(dy) > DRAG_SLOP) dragged = true;
    container.scrollLeft -= dx;
    container.scrollTop -= dy;
    origin = { x: event.clientX, y: event.clientY };
  });
  const end = () => {
    origin = null;
    container.classList.remove("panning");
  };
  svg.addEventListener("pointerup", end);
  svg.addEventListener("pointercancel", end);
  svg.addEventListener("dragstart", (event) => event.preventDefault());

  return {
    consumeDrag() {
      const was = dragged;
      dragged = false;
      return was;
    },
  };
}

function pinElement(pin, radius, context) {
  const { canWrite, selected, onSelect } = context;
  const name = pin.article.title || pin.article.id;
  const group = document.createElementNS(SVG_NS, "g");
  group.setAttribute("class", `pin${selected ? " selected" : ""}`);
  group.setAttribute("transform", translate(pin.position));
  group.setAttribute("tabindex", "0");
  group.setAttribute("role", "button");
  group.setAttribute("aria-label", name);

  const tooltip = document.createElementNS(SVG_NS, "title");
  tooltip.textContent = name;
  group.append(tooltip, disc(radius), core(radius), label(name, radius));

  group.addEventListener("click", (event) => {
    event.stopPropagation();
    onSelect(pin);
  });
  group.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    onSelect(pin);
  });
  if (canWrite) attachDrag(group, pin, context);
  return group;
}

function attachDrag(group, pin, { svg, viewBox, onMove }) {
  let origin = null;
  let position = null;

  const reset = () => {
    origin = null;
    position = null;
    group.classList.remove("dragging");
  };

  group.addEventListener("pointerdown", (event) => {
    if (event.button !== 0) return;
    event.stopPropagation();
    origin = { x: event.clientX, y: event.clientY };
    position = null;
    group.classList.add("dragging");
    group.setPointerCapture(event.pointerId);
  });
  group.addEventListener("pointermove", (event) => {
    if (!origin) return;
    // Under the slop threshold this is a click whose hand shook, not a drag;
    // treating it as a move would dirty the draft every time a pin is selected.
    if (Math.abs(event.clientX - origin.x) <= DRAG_SLOP
      && Math.abs(event.clientY - origin.y) <= DRAG_SLOP) return;
    const point = clientPoint(svg, event.clientX, event.clientY);
    // Outside the viewBox is not a valid location, so the pin stops at the
    // last place that was -- rather than snapping to an edge nobody pointed at.
    if (!insideViewBox(point, viewBox)) return;
    position = point;
    group.setAttribute("transform", translate(point));
  });
  group.addEventListener("pointerup", () => {
    if (!origin) return;
    const dropped = position;
    reset();
    if (dropped) onMove(pin, dropped);
  });
  group.addEventListener("pointercancel", () => {
    reset();
    group.setAttribute("transform", translate(pin.position));
  });
}

function disc(radius) {
  const circle = document.createElementNS(SVG_NS, "circle");
  circle.setAttribute("class", "pin-disc");
  circle.setAttribute("r", String(radius));
  return circle;
}

function core(radius) {
  const circle = document.createElementNS(SVG_NS, "circle");
  circle.setAttribute("class", "pin-core");
  circle.setAttribute("r", String(radius * 0.3));
  return circle;
}

function label(name, radius) {
  const text = document.createElementNS(SVG_NS, "text");
  text.setAttribute("class", "pin-label");
  text.setAttribute("x", String(radius * 1.5));
  text.setAttribute("y", String(radius * -0.4));
  text.setAttribute("font-size", String(radius * 1.9));
  text.setAttribute("stroke-width", String(radius * 0.3));
  text.textContent = name;
  return text;
}

function isSame(left, right) {
  return Boolean(right)
    && left.article.collection === right.article.collection
    && left.article.id === right.article.id;
}

function translate(point) {
  return `translate(${point.x} ${point.y})`;
}
