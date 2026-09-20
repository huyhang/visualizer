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
// The scrim at each end of the stage, which must match `.timeline-fade`'s height
// in visualizer.css -- the layout decides how strongly it is painted, and it can
// only do that if it knows how deep it is. Pinned by a test.
const FADE_H = 72;
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

// `cursorY` is where the rule sits in the stage, which is not always the middle
// -- see `cursorOffset`. Every layer of the rail has to be told the same one or
// they measure from different origins, so the caller works it out once per frame
// (it comes back from `visibleScenes`) and hands it to all of them.
export function visibleBreaks(scale, cursorTick, {
  viewportHeight = scale.viewportHeight, overscan = 100,
  cursorY = viewportHeight / 2,
} = {}) {
  const cursor = displayAtTick(scale.map, cursorTick);
  return scale.map.gaps.map((gap) => ({
    ...gap,
    y: cursorY + (gap.displayStart + gap.displayDuration / 2 - cursor)
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
  cursorY = viewportHeight / 2,
} = {}) {
  const cursor = displayAtTick(scale.map, cursorTick);
  const byTick = new Map();
  for (const band of bands || []) {
    const found = byTick.get(band.tick);
    if (found) found.labels.push(band.label);
    else byTick.set(band.tick, { tick: band.tick, level: band.level, labels: [band.label] });
  }
  return [...byTick.values()].map((band) => {
    const y = cursorY + (displayAtTick(scale.map, band.tick) - cursor) * scale.pixelsPerUnit;
    return { ...band, y, side: y < cursorY ? "above" : "below" };
  }).filter((band) => band.y >= -overscan && band.y <= viewportHeight + overscan);
}

// -- the cards around the cursor ----------------------------------------------

// The small set of cards worth materialising, already positioned, and where the
// rule they hang off ended up. `order` is a `storyOrder` result; positions are
// viewport-relative.
//
// Two reaches, not one. `reachPx` is how far from the rule a scene may be and
// still be worth mounting -- a whole stage, because with the rule travelling
// (see `cursorOffset`) one side of it can be nearly the full height. `fadePx` is
// the distance the opacity ramp is calibrated against, and stays half a stage so
// that widening the first did not quietly flatten the depth cue.
export function visibleScenes(order, scale, cursorTick, {
  viewportHeight = scale.viewportHeight,
  overscan = 180,
  maxScenes = 20,
  columns = 2,
} = {}) {
  const reachPx = viewportHeight + overscan;
  const fadePx = viewportHeight / 2 + overscan;
  const selected = nearestScenes(order.ordered, scale, cursorTick, {
    radiusPx: reachPx, maxScenes,
  });
  const lanes = assignLanes(selected, order.rank, columns);
  const cursorY = cursorOffset(lanes, cursorTick, viewportHeight, columns);
  const cards = placeCards(lanes, scale, cursorTick, {
    viewportHeight, columns, fadePx, cursorY,
  }).sort((a, b) => compareScenes(a.scene, b.scene));
  return { cards, cursorY, scrim: scrimFor(cards, viewportHeight) };
}

// How strongly to paint the scrim at each end of the stage, 0 to 1.
//
// It is there to dissolve the cards `overflow: hidden` is about to cut in half,
// so it is worth exactly as much as there is card underneath it. That used to be
// a safe thing not to think about, because the rule was pinned to the middle and
// the stage's first 72px were blank whenever the book started there. Now that
// the rule travels, the opening scene parks right under the top scrim -- and a
// scrim painted regardless washed it almost white, which is a worse bug than the
// blank it replaced. Nothing running off an edge means no scrim at that edge.
function scrimFor(cards, viewportHeight) {
  let above = 0;
  let below = 0;
  for (const card of cards) {
    above = Math.max(above, -card.top);
    below = Math.max(below, card.top + CARD_HEIGHT - viewportHeight);
  }
  const share = (depth) => Math.min(1, Math.max(0, depth / FADE_H));
  return { top: share(above), bottom: share(below) };
}

// How much room one side of the rule wants: a column is packed independently, so
// the side needs as much as its deepest column. `stackAway` sets the first card
// `CURSOR_GAP` clear of the rule and each one after it `CARD_GAP` further, which
// is the sum taken here.
function sideDepth(lanes, cursorTick, columns, before) {
  let deepest = 0;
  for (let side = 0; side < Math.max(1, columns); side += 1) {
    const many = lanes.filter((item) => item.side === side
      && (before ? item.tick <= cursorTick : item.tick > cursorTick)).length;
    if (!many) continue;
    deepest = Math.max(deepest, CURSOR_GAP + many * CARD_HEIGHT + (many - 1) * CARD_GAP);
  }
  return deepest;
}

// Where the rule sits in the stage.
//
// The middle, while the book runs past both edges of the lens -- which is all of
// the body of a book, and nothing here moves there. At the *ends* it does not:
// nothing precedes the first scene and nothing follows the last, so a rule
// pinned to the centre had half a lens with nothing to draw in it while scenes
// on the full side were being dropped for want of room. On a 568px stage that
// was 86px of blank above the opening view and 317px below the closing one, with
// seven cards mounted where eleven fit.
//
// So the rule travels through the last screenful at either end, the way a text
// caret does when the document runs out before the scrolloff does. It is pinned
// no lower than what the story above it needs and no higher than what the story
// below it needs; between those two bounds it wants the middle and gets it.
export function cursorOffset(lanes, cursorTick, viewportHeight, columns = 2) {
  const above = sideDepth(lanes, cursorTick, columns, true);
  const below = sideDepth(lanes, cursorTick, columns, false);
  // The rule carries its own reading in a pill centred on it, so it stops short
  // of the stage's edges even at the last scene, where the story below it has
  // run out completely and the bound above would otherwise put it on the border.
  const edge = Math.min(CURSOR_GAP, viewportHeight / 2);
  const settle = (y) => Math.min(Math.max(y, edge), viewportHeight - edge);
  // Neither side reaches an edge -- a short book, or a filter that left only a
  // handful. Centre what there is rather than pinning it against one end.
  if (above + below <= viewportHeight) {
    return settle(above + (viewportHeight - above - below) / 2);
  }
  // `EDGE_INSET` so a card parked at either end is clear of the stage's own
  // border rather than flush against it. A card *in transit* still runs past
  // the edge and is dissolved there -- see `scrimFor`.
  return settle(Math.min(
    Math.max(viewportHeight / 2, viewportHeight - below - EDGE_INSET),
    above + EDGE_INSET,
  ));
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
function placeCards(lanes, scale, cursorTick, {
  viewportHeight, columns, fadePx, cursorY,
}) {
  const anchored = lanes.map((item) => ({
    ...item, ...anchorsFor(item.scene, scale, cursorTick, viewportHeight, cursorY),
  }));
  const placed = [];
  for (let side = 0; side < Math.max(1, columns); side += 1) {
    const mine = anchored.filter((item) => item.side === side);
    const before = mine.filter((item) => item.tick <= cursorTick).reverse();
    const after = mine.filter((item) => item.tick > cursorTick);
    placed.push(
      ...stackAway(before, -1, { cursorY, viewportHeight }),
      ...stackAway(after, 1, { cursorY, viewportHeight }),
    );
  }
  return placed.map((item) => ({
    scene: item.scene,
    side: item.side,
    top: item.top,
    anchorY: item.anchorY,
    endY: item.endY,
    opacity: fadeFor(item.distancePx, viewportHeight, fadePx),
  }));
}

// Where a card's connector meets the rail. A long scene can still contain the
// cursor after its start has left the stage, so the connector is held at the
// edge rather than the card being dropped.
function anchorsFor(scene, scale, cursorTick, viewportHeight, cursorY) {
  const cursor = displayAtTick(scale.map, cursorTick);
  const at = (tick) => cursorY
    + (displayAtTick(scale.map, tick) - cursor) * scale.pixelsPerUnit;
  const held = (y) => Math.min(viewportHeight - EDGE_INSET, Math.max(EDGE_INSET, y));
  return { anchorY: held(at(scene.start_tick)), endY: held(at(scene.end_tick)) };
}

// One column, one direction: `step` is -1 for the cards above the cursor (given
// nearest-first, so reverse-chronological) and +1 for those below. Each card
// sits at its own anchor unless the one before it is in the way.
function stackAway(items, step, { cursorY, viewportHeight }) {
  let edge = step < 0 ? cursorY - CURSOR_GAP - CARD_HEIGHT : cursorY + CURSOR_GAP;
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
