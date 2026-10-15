// Pure geometry for the book-wide scene timeline, ported from the classic
// page's timelinelayout.js. The React shell (views/scenes/SceneTimeline.tsx)
// owns scrolling and DOM; keeping the clock maths here makes it testable and
// keeps scrolling independent of rendering.
//
// The shape: a vertical rail of time with a cursor rule across it. Cards hang
// either side of the rail, stacked *away* from the rule -- earlier scenes
// above it, later ones below -- and only the few nearest the cursor are
// mounted. Long empty stretches of the clock are compressed into "breaks" so a
// book with one scene at dawn and one a decade later is still two screens, not
// two hundred.

import { groupByPeriod, type TimedScene } from "../timeaxis";

const MIN_ZOOM = 0.5;
const MAX_ZOOM = 8;
export const CARD_HEIGHT = 78;
const CARD_GAP = 12;
const CURSOR_GAP = 30;
const EDGE_INSET = 12;
// The scrim at each end of the stage; must match `.cw-tl-fade`'s height in scenes.css.
export const FADE_H = 72;
const GAP_THRESHOLD_MULTIPLIER = 6;
const GAP_THRESHOLD_SHARE = 0.02;
const GAP_PIXELS = 140;

export const ZOOMS = [0.5, 1, 2, 4, 8] as const;

/** What the layout needs of a scene: an id, a title and two ticks. */
export interface RailScene extends TimedScene {
  id: string;
  title?: string;
  start_tick: number;
  end_tick: number;
}

export interface Bounds {
  start_tick: number;
  end_tick: number;
}

export interface Gap {
  startTick: number;
  endTick: number;
  rawDuration: number;
  displayStart: number;
  displayDuration: number;
  displayEnd: number;
}

export interface TimeMap {
  startTick: number;
  endTick: number;
  displaySpan: number;
  gaps: Gap[];
}

export interface Scale {
  startTick: number;
  endTick: number;
  span: number;
  map: TimeMap;
  zoom: number;
  viewportHeight: number;
  runHeight: number;
  contentHeight: number;
  pixelsPerUnit: number;
}

export interface StoryOrder<T extends RailScene> {
  ordered: T[];
  rank: Map<string, number>;
}

export interface Placement<T extends RailScene> {
  scene: T;
  side: number;
  top: number;
  anchorY: number;
  endY: number;
  opacity: number;
}

const titleOf = (scene: RailScene) => (scene.title || scene.id || "").toLowerCase();
const durationOf = (scene: RailScene) =>
  Math.max(0, Number(scene.end_tick) - Number(scene.start_tick));
const compareText = (a: string, b: string) => (a < b ? -1 : a > b ? 1 : 0);

/**
 * Same-time scenes are simultaneous, not sequential; this order only makes
 * their lanes deterministic: longest span, title, then permanent id.
 */
export function compareScenes(a: RailScene, b: RailScene): number {
  return (
    Number(a.start_tick) - Number(b.start_tick) ||
    durationOf(b) - durationOf(a) ||
    compareText(titleOf(a), titleOf(b)) ||
    compareText(String(a.id || ""), String(b.id || ""))
  );
}

/**
 * The book in story order, once. `visibleScenes` runs on every scroll frame and
 * a sort per frame is the one cost that grows with the book. `rank` is a
 * scene's permanent place, which keeps a card on one side as the window slides.
 */
export function storyOrder<T extends RailScene>(events: T[]): StoryOrder<T> {
  const ordered = [...events].sort(compareScenes);
  return { ordered, rank: new Map(ordered.map((scene, index) => [scene.id, index])) };
}

export const clampZoom = (zoom: number) =>
  Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, Number(zoom) || 1));

/** The next zoom step in `direction` (+1 in, -1 out), or the same one at the end of the range. */
export function stepZoom(zoom: number, direction: number): number {
  const at = (ZOOMS as readonly number[]).indexOf(zoom);
  const index = at < 0 ? 1 : at;
  return ZOOMS[Math.min(ZOOMS.length - 1, Math.max(0, index + direction))] ?? zoom;
}

export function scaleFor(
  bounds: Bounds,
  {
    viewportHeight,
    eventCount,
    events = [],
    zoom = 1,
  }: {
    viewportHeight: number;
    eventCount?: number;
    events?: RailScene[];
    zoom?: number;
  },
): Scale {
  const height = Math.max(320, Number(viewportHeight) || 0);
  const startTick = Number(bounds.start_tick);
  const rawEnd = Number(bounds.end_tick);
  const endTick = Number.isFinite(rawEnd) ? rawEnd : startTick;
  const safeZoom = clampZoom(zoom);
  // Enough travel for ordinary books to breathe, without making a thousand
  // scenes a browser-height document. Only nearby cards are mounted.
  const count = eventCount ?? events.length;
  const baseRun = Math.max(height, Math.max(1, count || 0) * 48);
  const runHeight = baseRun * safeZoom;
  const map = timeMap(events, { startTick, endTick, runHeight, zoom: safeZoom });
  return {
    startTick,
    endTick,
    span: Math.max(1, endTick - startTick),
    map,
    zoom: safeZoom,
    viewportHeight: height,
    runHeight,
    contentHeight: runHeight + height,
    pixelsPerUnit: runHeight / map.displaySpan,
  };
}

export function tickAtScroll(scale: Scale, scrollTop: number): number {
  const ratio = Math.min(1, Math.max(0, Number(scrollTop) / scale.runHeight));
  return Math.round(tickAtDisplay(scale.map, ratio * scale.map.displaySpan));
}

export function scrollForTick(scale: Scale, tick: number): number {
  const ratio = displayAtTick(scale.map, tick) / scale.map.displaySpan;
  return Math.min(scale.runHeight, Math.max(0, ratio * scale.runHeight));
}

export function ratioForTick(scale: Scale, tick: number): number {
  return Math.min(1, Math.max(0, displayAtTick(scale.map, tick) / scale.map.displaySpan));
}

export function tickAtRatio(scale: Scale, ratio: number): number {
  const bounded = Math.min(1, Math.max(0, Number(ratio)));
  return Math.round(tickAtDisplay(scale.map, bounded * scale.map.displaySpan));
}

export function distanceToScene(scene: RailScene, tick: number): number {
  const start = Number(scene.start_tick);
  const end = Number(scene.end_tick);
  if (tick < start) return start - tick;
  if (tick > end) return tick - end;
  return 0;
}

/** How many scenes start in each of `count` slices of the run: the overview's density marks. */
export function densityBins(events: RailScene[], scale: Scale, count = 48): number[] {
  const size = Math.max(1, Math.floor(count));
  const bins: number[] = Array(size).fill(0);
  for (const scene of events) {
    const ratio = ratioForTick(scale, scene.start_tick);
    const index = Math.min(size - 1, Math.max(0, Math.floor(ratio * size)));
    bins[index] = (bins[index] ?? 0) + 1;
  }
  return bins;
}

/** The compressed stretches near the cursor, positioned against the same rule as the cards. */
export function visibleBreaks(
  scale: Scale,
  cursorTick: number,
  options: { viewportHeight?: number; overscan?: number; cursorY?: number } = {},
): (Gap & { y: number })[] {
  const { viewportHeight = scale.viewportHeight, overscan = 100 } = options;
  const cursorY = options.cursorY ?? viewportHeight / 2;
  const cursor = displayAtTick(scale.map, cursorTick);
  return scale.map.gaps
    .map((gap) => ({
      ...gap,
      y:
        cursorY +
        (gap.displayStart + gap.displayDuration / 2 - cursor) * scale.pixelsPerUnit,
    }))
    .filter((gap) => gap.y >= -overscan && gap.y <= viewportHeight + overscan);
}

// -- the book's own periods ---------------------------------------------------

export interface Band {
  tick: number;
  level: number;
  label: string;
}

/**
 * Where the calendar turns over, as ticks. Borrowed from the thread view's
 * `groupByPeriod`, so the two cannot disagree about where a period starts.
 */
export function periodBands(ordered: RailScene[]): Band[] {
  const bands: Band[] = [];
  let pending: { level: number; label: string }[] = [];
  for (const item of groupByPeriod(ordered)) {
    if (item.type === "header") {
      pending.push(item);
      continue;
    }
    for (const header of pending) {
      bands.push({
        tick: Number(item.event.start_tick),
        level: header.level,
        label: header.label,
      });
    }
    pending = [];
  }
  return bands;
}

export interface PeriodMark {
  tick: number;
  level: number;
  labels: string[];
  y: number;
  /** Which way the label hangs off its rule: always away from the cursor, so the two never overprint. */
  side: "above" | "below";
}

/** The bands near the cursor; levels turning over together are one boundary. */
export function visiblePeriods(
  bands: Band[],
  scale: Scale,
  cursorTick: number,
  options: { viewportHeight?: number; overscan?: number; cursorY?: number } = {},
): PeriodMark[] {
  const { viewportHeight = scale.viewportHeight, overscan = 40 } = options;
  const cursorY = options.cursorY ?? viewportHeight / 2;
  const cursor = displayAtTick(scale.map, cursorTick);
  const byTick = new Map<number, { tick: number; level: number; labels: string[] }>();
  for (const band of bands) {
    const found = byTick.get(band.tick);
    if (found) found.labels.push(band.label);
    else
      byTick.set(band.tick, { tick: band.tick, level: band.level, labels: [band.label] });
  }
  return [...byTick.values()]
    .map((band) => {
      const y =
        cursorY + (displayAtTick(scale.map, band.tick) - cursor) * scale.pixelsPerUnit;
      return { ...band, y, side: y < cursorY ? ("above" as const) : ("below" as const) };
    })
    .filter((band) => band.y >= -overscan && band.y <= viewportHeight + overscan);
}

// -- the cards around the cursor ----------------------------------------------

interface Ranked<T extends RailScene> {
  scene: T;
  distancePx: number;
  distance: number;
}

interface Laned<T extends RailScene> extends Ranked<T> {
  tick: number;
  side: number;
}

export interface Frame<T extends RailScene> {
  cards: Placement<T>[];
  cursorY: number;
  scrim: { top: number; bottom: number };
}

/**
 * The few cards worth mounting, positioned, and where the rule they hang off
 * ended up. Two reaches: `reachPx` decides what is mounted (a whole stage, as
 * the rule travels), `fadePx` what the opacity ramp is calibrated against.
 */
export function visibleScenes<T extends RailScene>(
  order: StoryOrder<T>,
  scale: Scale,
  cursorTick: number,
  {
    viewportHeight = scale.viewportHeight,
    overscan = 180,
    maxScenes = 20,
    columns = 2,
  } = {},
): Frame<T> {
  const reachPx = viewportHeight + overscan;
  const fadePx = viewportHeight / 2 + overscan;
  const selected = nearestScenes(order.ordered, scale, cursorTick, {
    radiusPx: reachPx,
    maxScenes,
  });
  const lanes = assignLanes(selected, order.rank, columns);
  const cursorY = cursorOffset(lanes, cursorTick, viewportHeight, columns);
  const cards = placeCards(lanes, scale, cursorTick, {
    viewportHeight,
    columns,
    fadePx,
    cursorY,
  }).sort((a, b) => compareScenes(a.scene, b.scene));
  return { cards, cursorY, scrim: scrimFor(cards, viewportHeight) };
}

/** How strongly to paint each end's scrim: as much as there is card running off that edge. */
function scrimFor(cards: { top: number }[], viewportHeight: number) {
  let above = 0;
  let below = 0;
  for (const card of cards) {
    above = Math.max(above, -card.top);
    below = Math.max(below, card.top + CARD_HEIGHT - viewportHeight);
  }
  const share = (depth: number) => Math.min(1, Math.max(0, depth / FADE_H));
  return { top: share(above), bottom: share(below) };
}

function sideDepth(
  lanes: { side: number; tick: number }[],
  cursorTick: number,
  columns: number,
  before: boolean,
) {
  let deepest = 0;
  for (let side = 0; side < Math.max(1, columns); side += 1) {
    const many = lanes.filter(
      (item) =>
        item.side === side && (before ? item.tick <= cursorTick : item.tick > cursorTick),
    ).length;
    if (!many) continue;
    deepest = Math.max(deepest, CURSOR_GAP + many * CARD_HEIGHT + (many - 1) * CARD_GAP);
  }
  return deepest;
}

/**
 * Where the rule sits in the stage: the middle through the body of a book, but
 * travelling through the last screenful at either end -- the way a caret does
 * when the document runs out -- so neither end opens on half a lens of blank.
 */
export function cursorOffset(
  lanes: { side: number; tick: number }[],
  cursorTick: number,
  viewportHeight: number,
  columns = 2,
): number {
  const above = sideDepth(lanes, cursorTick, columns, true);
  const below = sideDepth(lanes, cursorTick, columns, false);
  const edge = Math.min(CURSOR_GAP, viewportHeight / 2);
  const settle = (y: number) => Math.min(Math.max(y, edge), viewportHeight - edge);
  if (above + below <= viewportHeight)
    return settle(above + (viewportHeight - above - below) / 2);
  return settle(
    Math.min(
      Math.max(viewportHeight / 2, viewportHeight - below - EDGE_INSET),
      above + EDGE_INSET,
    ),
  );
}

/** Nearest first, within reach, capped -- but never cutting a simultaneous moment in half. */
function nearestScenes<T extends RailScene>(
  ordered: T[],
  scale: Scale,
  cursorTick: number,
  { radiusPx, maxScenes }: { radiusPx: number; maxScenes: number },
): Ranked<T>[] {
  const ranked: Ranked<T>[] = [];
  for (const scene of ordered) {
    const distancePx = distancePixels(scale, scene, cursorTick);
    if (distancePx > radiusPx) continue;
    ranked.push({ scene, distancePx, distance: distanceToScene(scene, cursorTick) });
  }
  ranked.sort((a, b) => a.distance - b.distance || compareScenes(a.scene, b.scene));
  const cutoffTick = ranked[Math.min(maxScenes, ranked.length) - 1]?.scene.start_tick;
  return ranked
    .filter((item, index) => index < maxScenes || item.scene.start_tick === cutoffTick)
    .sort((a, b) => compareScenes(a.scene, b.scene));
}

/** Same-tick cards alternate sides, starting from the scene's permanent rank so nothing hops. */
function assignLanes<T extends RailScene>(
  selected: Ranked<T>[],
  rank: Map<string, number>,
  columns: number,
): Laned<T>[] {
  const lanes = new Map<number, { base: number; count: number }>();
  return selected.map((item) => {
    const tick = Number(item.scene.start_tick);
    const lane = lanes.get(tick) ?? {
      base: (rank.get(item.scene.id) ?? 0) % columns,
      count: 0,
    };
    lanes.set(tick, { base: lane.base, count: lane.count + 1 });
    return { ...item, tick, side: columns > 1 ? (lane.base + lane.count) % columns : 0 };
  });
}

/**
 * Cards are laid out outward from the cursor, never across it. A card that
 * still does not fit is dropped rather than hidden behind the stage's edge.
 */
function placeCards<T extends RailScene>(
  lanes: Laned<T>[],
  scale: Scale,
  cursorTick: number,
  {
    viewportHeight,
    columns,
    fadePx,
    cursorY,
  }: { viewportHeight: number; columns: number; fadePx: number; cursorY: number },
): Placement<T>[] {
  const anchored = lanes.map((item) => ({
    ...item,
    ...anchorsFor(item.scene, scale, cursorTick, viewportHeight, cursorY),
  }));
  const placed: ((typeof anchored)[number] & { top: number })[] = [];
  for (let side = 0; side < Math.max(1, columns); side += 1) {
    const mine = anchored.filter((item) => item.side === side);
    const before = mine.filter((item) => item.tick <= cursorTick).reverse();
    const after = mine.filter((item) => item.tick > cursorTick);
    placed.push(
      ...stackAway(before, -1, cursorY, viewportHeight),
      ...stackAway(after, 1, cursorY, viewportHeight),
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

/** Where a card's connector meets the rail, held at the edge for a long scene still spanning the cursor. */
function anchorsFor(
  scene: RailScene,
  scale: Scale,
  cursorTick: number,
  viewportHeight: number,
  cursorY: number,
) {
  const cursor = displayAtTick(scale.map, cursorTick);
  const at = (tick: number) =>
    cursorY + (displayAtTick(scale.map, tick) - cursor) * scale.pixelsPerUnit;
  const held = (y: number) =>
    Math.min(viewportHeight - EDGE_INSET, Math.max(EDGE_INSET, y));
  return { anchorY: held(at(scene.start_tick)), endY: held(at(scene.end_tick)) };
}

function stackAway<I extends { anchorY: number }>(
  items: I[],
  step: number,
  cursorY: number,
  viewportHeight: number,
) {
  let edge = step < 0 ? cursorY - CURSOR_GAP - CARD_HEIGHT : cursorY + CURSOR_GAP;
  const out: (I & { top: number })[] = [];
  for (const item of items) {
    const wanted = item.anchorY - CARD_HEIGHT / 2;
    const top = step < 0 ? Math.min(wanted, edge) : Math.max(wanted, edge);
    if (top + CARD_HEIGHT <= 0 || top >= viewportHeight) break;
    out.push({ ...item, top });
    edge = step < 0 ? top - CARD_HEIGHT - CARD_GAP : top + CARD_HEIGHT + CARD_GAP;
  }
  return out;
}

/** Distance reads as depth: cards under the cursor are solid, those at the edge of reach nearly gone. */
function fadeFor(distancePx: number, viewportHeight: number, radiusPx: number) {
  const fadeStart = viewportHeight * 0.28;
  const fadeSpan = Math.max(1, radiusPx - fadeStart);
  return 1 - Math.min(0.68, (Math.max(0, distancePx - fadeStart) / fadeSpan) * 0.68);
}

function distancePixels(scale: Scale, scene: RailScene, tick: number) {
  if (tick < scene.start_tick) {
    return (
      (displayAtTick(scale.map, scene.start_tick) - displayAtTick(scale.map, tick)) *
      scale.pixelsPerUnit
    );
  }
  if (tick > scene.end_tick) {
    return (
      (displayAtTick(scale.map, tick) - displayAtTick(scale.map, scene.end_tick)) *
      scale.pixelsPerUnit
    );
  }
  return 0;
}

// -- compressing the empty stretches ------------------------------------------

function timeMap(
  events: RailScene[],
  {
    startTick,
    endTick,
    runHeight,
    zoom,
  }: { startTick: number; endTick: number; runHeight: number; zoom: number },
): TimeMap {
  const rawSpan = Math.max(1, endTick - startTick);
  const occupied = mergedIntervals(events, startTick, endTick);
  const durations = events
    .map(durationOf)
    .filter((d) => d > 0)
    .sort((a, b) => a - b);
  const baseline = median(durations) || rawSpan;
  const threshold = Math.max(
    baseline * GAP_THRESHOLD_MULTIPLIER,
    rawSpan * GAP_THRESHOLD_SHARE,
  );
  const candidates: { startTick: number; endTick: number }[] = [];
  for (let index = 1; index < occupied.length; index += 1) {
    const start = occupied[index - 1]!.end;
    const end = occupied[index]!.start;
    if (end - start > threshold) candidates.push({ startTick: start, endTick: end });
  }
  if (!candidates.length) return { startTick, endTick, displaySpan: rawSpan, gaps: [] };

  const compressedRaw = candidates.reduce(
    (total, gap) => total + gap.endTick - gap.startTick,
    0,
  );
  const otherRaw = Math.max(1, rawSpan - compressedRaw);
  const targetPixels = Math.min(
    GAP_PIXELS * Math.sqrt(zoom),
    runHeight / (candidates.length * 2 + 1),
  );
  const remainingPixels = Math.max(1, runHeight - targetPixels * candidates.length);
  const displayDuration = (targetPixels * otherRaw) / remainingPixels;
  let reduction = 0;
  const gaps = candidates.map((gap) => {
    const rawDuration = gap.endTick - gap.startTick;
    const displayStart = gap.startTick - startTick - reduction;
    reduction += rawDuration - displayDuration;
    return {
      ...gap,
      rawDuration,
      displayStart,
      displayDuration,
      displayEnd: displayStart + displayDuration,
    };
  });
  return { startTick, endTick, displaySpan: rawSpan - reduction, gaps };
}

function mergedIntervals(events: RailScene[], startTick: number, endTick: number) {
  const intervals = events
    .map((scene) => ({
      start: Math.max(startTick, Number(scene.start_tick)),
      end: Math.min(endTick, Number(scene.end_tick)),
    }))
    .sort((a, b) => a.start - b.start || a.end - b.end);
  const merged: { start: number; end: number }[] = [];
  for (const interval of intervals) {
    const last = merged[merged.length - 1];
    if (last && interval.start <= last.end) last.end = Math.max(last.end, interval.end);
    else merged.push({ ...interval });
  }
  return merged;
}

function median(values: number[]): number {
  if (!values.length) return 0;
  const middle = Math.floor(values.length / 2);
  return values.length % 2 ? values[middle]! : (values[middle - 1]! + values[middle]!) / 2;
}

function displayAtTick(map: TimeMap, tick: number): number {
  const bounded = Math.min(map.endTick, Math.max(map.startTick, Number(tick)));
  let reduction = 0;
  for (const gap of map.gaps) {
    if (bounded >= gap.endTick) {
      reduction += gap.rawDuration - gap.displayDuration;
      continue;
    }
    if (bounded > gap.startTick) {
      return (
        gap.displayStart +
        ((bounded - gap.startTick) / gap.rawDuration) * gap.displayDuration
      );
    }
    break;
  }
  return bounded - map.startTick - reduction;
}

function tickAtDisplay(map: TimeMap, display: number): number {
  const bounded = Math.min(map.displaySpan, Math.max(0, Number(display)));
  let reduction = 0;
  for (const gap of map.gaps) {
    if (bounded >= gap.displayEnd) {
      reduction += gap.rawDuration - gap.displayDuration;
      continue;
    }
    if (bounded > gap.displayStart) {
      return (
        gap.startTick +
        ((bounded - gap.displayStart) / gap.displayDuration) * gap.rawDuration
      );
    }
    break;
  }
  return map.startTick + bounded + reduction;
}

/** Every tick the payload already dates, as [tick, label] pairs: the cursor label's free answers. */
export function seedLabels(events: RailScene[]): [number, string][] {
  const pairs: [number, string][] = [];
  for (const scene of events) {
    if (scene.start_label) pairs.push([Number(scene.start_tick), scene.start_label]);
    if (scene.end_label) pairs.push([Number(scene.end_tick), scene.end_label]);
  }
  return pairs;
}

/**
 * What the stage shows at one column: on a narrow screen, same-tick scenes
 * fold into one "moment" card rather than stacking down a single side.
 */
export function displayPlacements<T extends RailScene>(
  placements: Placement<T>[],
  columns: number,
): { key: string; placement: Placement<T>; scenes: T[] }[] {
  if (columns > 1)
    return placements.map((placement) => ({
      key: placement.scene.id,
      placement,
      scenes: [placement.scene],
    }));
  const grouped = new Map<string, { key: string; placement: Placement<T>; scenes: T[] }>();
  for (const placement of placements) {
    const key = String(placement.scene.start_tick);
    const found = grouped.get(key);
    if (found) found.scenes.push(placement.scene);
    else grouped.set(key, { key: `moment:${key}`, placement, scenes: [placement.scene] });
  }
  return [...grouped.values()].map((item) =>
    item.scenes.length === 1 ? { ...item, key: item.scenes[0]!.id } : item,
  );
}

/** The CSS geometry of one rail item: where its anchor, span bar and stem fall inside the card. */
export function railGeometry(placement: { top: number; anchorY: number; endY: number }) {
  const cardCenter = CARD_HEIGHT / 2;
  const anchor = placement.anchorY - placement.top;
  const end = placement.endY - placement.top;
  return {
    anchor,
    durationTop: Math.min(anchor, end),
    durationHeight: Math.max(3, Math.abs(end - anchor)),
    stemTop: Math.min(anchor, cardCenter),
    stemHeight: Math.max(2, Math.abs(anchor - cardCenter)),
  };
}
