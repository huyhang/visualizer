// Pure geometry for the book-wide scene timeline. DOM and input handling live
// in scenetimeline.js; keeping the clock math here makes the behavior testable
// under Node and keeps scrolling independent from rendering.

import { groupByPeriod } from "./timeaxis.js";

const MIN_ZOOM = 0.5;
const MAX_ZOOM = 8;
const CARD_HEIGHT = 78;
const CARD_GAP = 12;
const CURSOR_GAP = 30;
const EDGE_INSET = 12;
const GAP_THRESHOLD_MULTIPLIER = 6;
const GAP_THRESHOLD_SHARE = 0.02;
const GAP_PIXELS = 140;

const titleOf = (scene) => (scene.title || scene.id || "").toLowerCase();
const durationOf = (scene) => Math.max(0, Number(scene.end_tick) - Number(scene.start_tick));
const compareText = (a, b) => (a < b ? -1 : a > b ? 1 : 0);

// Same-time scenes are simultaneous, not sequential. This order only makes
// their lanes deterministic: longest span, title, then permanent id.
export function compareScenes(a, b) {
  return (Number(a.start_tick) - Number(b.start_tick))
    || (durationOf(b) - durationOf(a))
    || compareText(titleOf(a), titleOf(b))
    || compareText(String(a.id || ""), String(b.id || ""));
}

// The book in story order, once. Every later call reads this rather than
// re-sorting: `visibleScenes` runs on every scroll frame, and a sort per frame
// is the one cost that grows with the size of the book. `rank` is a scene's
// permanent place in that order, which is what keeps a card on the same side of
// the rail as the window slides past it.
export function storyOrder(events) {
  const ordered = [...(events || [])].sort(compareScenes);
  return { ordered, rank: new Map(ordered.map((scene, index) => [scene.id, index])) };
}

export function scaleFor(bounds, { viewportHeight, eventCount, events = [], zoom = 1 } = {}) {
  const height = Math.max(320, Number(viewportHeight) || 0);
  const startTick = Number(bounds && bounds.start_tick);
  const rawEnd = Number(bounds && bounds.end_tick);
  const endTick = Number.isFinite(rawEnd) ? rawEnd : startTick;
  const safeZoom = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, Number(zoom) || 1));
  // Enough travel for ordinary books to breathe, without making a thousand
  // scenes into a browser-height document. Only nearby cards enter the DOM.
  const count = eventCount == null ? events.length : eventCount;
  const baseRun = Math.max(height, Math.max(1, count || 0) * 48);
  const runHeight = baseRun * safeZoom;
  const map = timeMap(events, { startTick, endTick, runHeight, zoom: safeZoom });
  return {
    startTick, endTick, span: Math.max(1, endTick - startTick), map,
    zoom: safeZoom, viewportHeight: height,
    runHeight, contentHeight: runHeight + height,
    pixelsPerTick: runHeight / map.displaySpan,
    pixelsPerUnit: runHeight / map.displaySpan,
  };
}

export function tickAtScroll(scale, scrollTop) {
  const ratio = Math.min(1, Math.max(0, Number(scrollTop) / scale.runHeight));
  return Math.round(tickAtDisplay(scale.map, ratio * scale.map.displaySpan));
}

export function scrollForTick(scale, tick) {
  const ratio = displayAtTick(scale.map, tick) / scale.map.displaySpan;
  return Math.min(scale.runHeight, Math.max(0, ratio * scale.runHeight));
}

export function ratioForTick(scale, tick) {
  return Math.min(1, Math.max(0, displayAtTick(scale.map, tick) / scale.map.displaySpan));
}

export function tickAtRatio(scale, ratio) {
  const bounded = Math.min(1, Math.max(0, Number(ratio)));
  return Math.round(tickAtDisplay(scale.map, bounded * scale.map.displaySpan));
}

export function distanceToScene(scene, tick) {
  const start = Number(scene.start_tick);
  const end = Number(scene.end_tick);
  if (tick < start) return start - tick;
  if (tick > end) return tick - end;
  return 0;
}

export function densityBins(events, scale, count = 48) {
  const size = Math.max(1, Math.floor(count));
  const bins = Array(size).fill(0);
  for (const scene of events || []) {
    const ratio = ratioForTick(scale, scene.start_tick);
    const index = Math.min(size - 1, Math.max(0, Math.floor(ratio * size)));
    bins[index] += 1;
  }
  return bins;
}

export function visibleBreaks(scale, cursorTick, {
  viewportHeight = scale.viewportHeight, overscan = 100,
} = {}) {
  const center = viewportHeight / 2;
  const cursor = displayAtTick(scale.map, cursorTick);
  return scale.map.gaps.map((gap) => ({
    ...gap,
    y: center + (gap.displayStart + gap.displayDuration / 2 - cursor)
      * scale.pixelsPerUnit,
  })).filter((gap) => gap.y >= -overscan && gap.y <= viewportHeight + overscan);
}

// -- the book's own periods ---------------------------------------------------

// Where the calendar turns over, as ticks. `groupByPeriod` already knows how to
// read a codec's coarse-to-fine parts -- whatever the cycles are called and
// however deep they go -- so the rail borrows the plotline view's grouping
// rather than growing a second, disagreeing one. A bare-tick book has no
// component coarser than its clock, so it gets no bands at all.
export function periodBands(ordered) {
  const bands = [];
  let pending = [];
  for (const item of groupByPeriod(ordered || [])) {
    if (item.type === "header") {
      pending.push(item);
      continue;
    }
    for (const header of pending) {
      bands.push({
        tick: Number(item.event.start_tick), level: header.level, label: header.label,
      });
    }
    pending = [];
  }
  return bands;
}

// The bands near the cursor, positioned. Levels that turn over together -- a new
// year is also a new month -- are one boundary on the rail, read coarse-to-fine,
// because drawing them at the same pixel twice would just overprint.
//
// `side` is which way the band hangs its label off its own rule, and it is the
// whole answer to a collision: the cursor's rule is drawn two layers above the
// bands, so a label sitting *on* its rule gets the accent line straight through
// it whenever a period turns over near the cursor. Hanging the label on the far
// side from the cursor means the two can never occupy the same pixels -- and,
// unlike hiding the band, it still reads at the one position the rail opens in,
// where the cursor is parked exactly on the book's first boundary.
export function visiblePeriods(bands, scale, cursorTick, {
  viewportHeight = scale.viewportHeight, overscan = 40,
} = {}) {
  const center = viewportHeight / 2;
  const cursor = displayAtTick(scale.map, cursorTick);
  const byTick = new Map();
  for (const band of bands || []) {
    const found = byTick.get(band.tick);
    if (found) found.labels.push(band.label);
    else byTick.set(band.tick, { tick: band.tick, level: band.level, labels: [band.label] });
  }
  return [...byTick.values()].map((band) => {
    const y = center + (displayAtTick(scale.map, band.tick) - cursor) * scale.pixelsPerUnit;
    return { ...band, y, side: y < center ? "above" : "below" };
  }).filter((band) => band.y >= -overscan && band.y <= viewportHeight + overscan);
}

// -- the cards around the cursor ----------------------------------------------

// The small set of cards worth materialising, already positioned. `order` is a
// `storyOrder` result; positions are viewport-relative.
export function visibleScenes(order, scale, cursorTick, {
  viewportHeight = scale.viewportHeight,
  overscan = 180,
  maxScenes = 20,
  columns = 2,
} = {}) {
  const radiusPx = viewportHeight / 2 + overscan;
  const selected = nearestScenes(order.ordered, scale, cursorTick, { radiusPx, maxScenes });
  const lanes = assignLanes(selected, order.rank, columns);
  return placeCards(lanes, scale, cursorTick, {
    viewportHeight, columns, radiusPx,
  }).sort((a, b) => compareScenes(a.scene, b.scene));
}

// Nearest the cursor first, within a stage's reach of it, capped -- but never
// cutting a simultaneous moment in half, since hiding the 21st of 21 scenes at
// this exact tick would be a lie about the book. Returned in story order.
function nearestScenes(ordered, scale, cursorTick, { radiusPx, maxScenes }) {
  const ranked = [];
  for (const scene of ordered) {
    const distancePx = distancePixels(scale, scene, cursorTick);
    if (distancePx > radiusPx) continue;
    ranked.push({ scene, distancePx, distance: distanceToScene(scene, cursorTick) });
  }
  ranked.sort((a, b) => (a.distance - b.distance) || compareScenes(a.scene, b.scene));
  const cutoffTick = ranked[Math.min(maxScenes, ranked.length) - 1]?.scene.start_tick;
  return ranked
    .filter((item, index) => index < maxScenes || item.scene.start_tick === cutoffTick)
    .sort((a, b) => compareScenes(a.scene, b.scene));
}

// A card's column. Cards at the same tick alternate sides so simultaneous
// scenes read as parallel; the run starts from the scene's permanent place in
// story order, so a card does not hop sides as the window slides past it.
function assignLanes(selected, rank, columns) {
  const lanes = new Map();
  return selected.map((item) => {
    const tick = Number(item.scene.start_tick);
    const lane = lanes.get(tick) || { base: (rank.get(item.scene.id) ?? 0) % columns, count: 0 };
    lanes.set(tick, { base: lane.base, count: lane.count + 1 });
    return { ...item, tick, side: columns > 1 ? (lane.base + lane.count) % columns : 0 };
  });
}

// Cards are laid out *outward from the cursor*, never across it: those at or
// before it stack upward from just above the rule, those after it stack
// downward from just below. Packing everything in one direction -- the obvious
// way -- pushed the later half of the window off the bottom of the stage, where
// it stayed mounted and invisible; on the Salt Road book that was two cards in
// five. A card that still does not fit is dropped rather than hidden, and the
// run stops there, because every card behind it is further out again.
function placeCards(lanes, scale, cursorTick, { viewportHeight, columns, radiusPx }) {
  const center = viewportHeight / 2;
  const anchored = lanes.map((item) => ({
    ...item, ...anchorsFor(item.scene, scale, cursorTick, viewportHeight),
  }));
  const placed = [];
  for (let side = 0; side < Math.max(1, columns); side += 1) {
    const mine = anchored.filter((item) => item.side === side);
    const before = mine.filter((item) => item.tick <= cursorTick).reverse();
    const after = mine.filter((item) => item.tick > cursorTick);
    placed.push(
      ...stackAway(before, -1, { center, viewportHeight }),
      ...stackAway(after, 1, { center, viewportHeight }),
    );
  }
  return placed.map((item) => ({
    scene: item.scene,
    side: item.side,
    top: item.top,
    anchorY: item.anchorY,
    endY: item.endY,
    opacity: fadeFor(item.distancePx, viewportHeight, radiusPx),
  }));
}

// Where a card's connector meets the rail. A long scene can still contain the
// cursor after its start has left the stage, so the connector is held at the
// edge rather than the card being dropped.
function anchorsFor(scene, scale, cursorTick, viewportHeight) {
  const center = viewportHeight / 2;
  const cursor = displayAtTick(scale.map, cursorTick);
  const at = (tick) => center
    + (displayAtTick(scale.map, tick) - cursor) * scale.pixelsPerUnit;
  const held = (y) => Math.min(viewportHeight - EDGE_INSET, Math.max(EDGE_INSET, y));
  return { anchorY: held(at(scene.start_tick)), endY: held(at(scene.end_tick)) };
}

// One column, one direction: `step` is -1 for the cards above the cursor (given
// nearest-first, so reverse-chronological) and +1 for those below. Each card
// sits at its own anchor unless the one before it is in the way.
function stackAway(items, step, { center, viewportHeight }) {
  let edge = step < 0 ? center - CURSOR_GAP - CARD_HEIGHT : center + CURSOR_GAP;
  const out = [];
  for (const item of items) {
    const wanted = item.anchorY - CARD_HEIGHT / 2;
    const top = step < 0 ? Math.min(wanted, edge) : Math.max(wanted, edge);
    if (top + CARD_HEIGHT <= 0 || top >= viewportHeight) break;
    out.push({ ...item, top });
    edge = step < 0 ? top - CARD_HEIGHT - CARD_GAP : top + CARD_HEIGHT + CARD_GAP;
  }
  return out;
}

// Distance reads as depth: the cards under the cursor are solid, the ones at
// the edge of its reach are nearly gone.
function fadeFor(distancePx, viewportHeight, radiusPx) {
  const fadeStart = viewportHeight * 0.28;
  const fadeSpan = Math.max(1, radiusPx - fadeStart);
  return 1 - Math.min(0.68, Math.max(0, distancePx - fadeStart) / fadeSpan * 0.68);
}

function distancePixels(scale, scene, tick) {
  if (tick < scene.start_tick) {
    return (displayAtTick(scale.map, scene.start_tick) - displayAtTick(scale.map, tick))
      * scale.pixelsPerUnit;
  }
  if (tick > scene.end_tick) {
    return (displayAtTick(scale.map, tick) - displayAtTick(scale.map, scene.end_tick))
      * scale.pixelsPerUnit;
  }
  return 0;
}

// -- compressing the empty stretches ------------------------------------------

function timeMap(events, { startTick, endTick, runHeight, zoom }) {
  const rawSpan = Math.max(1, endTick - startTick);
  const occupied = mergedIntervals(events, startTick, endTick);
  const durations = (events || []).map(durationOf).filter((duration) => duration > 0)
    .sort((a, b) => a - b);
  const baseline = median(durations) || rawSpan;
  const threshold = Math.max(
    baseline * GAP_THRESHOLD_MULTIPLIER,
    rawSpan * GAP_THRESHOLD_SHARE,
  );
  const candidates = [];
  for (let index = 1; index < occupied.length; index += 1) {
    const start = occupied[index - 1].end;
    const end = occupied[index].start;
    if (end - start > threshold) candidates.push({ startTick: start, endTick: end });
  }
  if (!candidates.length) return { startTick, endTick, displaySpan: rawSpan, gaps: [] };

  const compressedRaw = candidates.reduce(
    (total, gap) => total + gap.endTick - gap.startTick, 0,
  );
  const otherRaw = Math.max(1, rawSpan - compressedRaw);
  const targetPixels = Math.min(
    GAP_PIXELS * Math.sqrt(zoom),
    runHeight / (candidates.length * 2 + 1),
  );
  const remainingPixels = Math.max(1, runHeight - targetPixels * candidates.length);
  const displayDuration = targetPixels * otherRaw / remainingPixels;
  let reduction = 0;
  const gaps = candidates.map((gap) => {
    const rawDuration = gap.endTick - gap.startTick;
    const displayStart = gap.startTick - startTick - reduction;
    const out = {
      ...gap, rawDuration, displayStart, displayDuration,
      displayEnd: displayStart + displayDuration,
    };
    reduction += rawDuration - displayDuration;
    return out;
  });
  return { startTick, endTick, displaySpan: rawSpan - reduction, gaps };
}

function mergedIntervals(events, startTick, endTick) {
  const intervals = (events || []).map((scene) => ({
    start: Math.max(startTick, Number(scene.start_tick)),
    end: Math.min(endTick, Number(scene.end_tick)),
  })).sort((a, b) => (a.start - b.start) || (a.end - b.end));
  const merged = [];
  for (const interval of intervals) {
    const last = merged[merged.length - 1];
    if (last && interval.start <= last.end) last.end = Math.max(last.end, interval.end);
    else merged.push({ ...interval });
  }
  return merged;
}

function median(values) {
  if (!values.length) return 0;
  const middle = Math.floor(values.length / 2);
  return values.length % 2
    ? values[middle]
    : (values[middle - 1] + values[middle]) / 2;
}

function displayAtTick(map, tick) {
  const bounded = Math.min(map.endTick, Math.max(map.startTick, Number(tick)));
  let reduction = 0;
  for (const gap of map.gaps) {
    if (bounded >= gap.endTick) {
      reduction += gap.rawDuration - gap.displayDuration;
      continue;
    }
    if (bounded > gap.startTick) {
      const ratio = (bounded - gap.startTick) / gap.rawDuration;
      return gap.displayStart + ratio * gap.displayDuration;
    }
    break;
  }
  return bounded - map.startTick - reduction;
}

function tickAtDisplay(map, display) {
  const bounded = Math.min(map.displaySpan, Math.max(0, Number(display)));
  let reduction = 0;
  for (const gap of map.gaps) {
    if (bounded >= gap.displayEnd) {
      reduction += gap.rawDuration - gap.displayDuration;
      continue;
    }
    if (bounded > gap.displayStart) {
      const ratio = (bounded - gap.displayStart) / gap.displayDuration;
      return gap.startTick + ratio * gap.rawDuration;
    }
    break;
  }
  return map.startTick + bounded + reduction;
}
