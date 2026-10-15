// One colour per thread, the same on every screen.
//
// A thread's colour is keyed to its place in the whole book (by id, the order
// the story graph lists them in), so it never shifts when a filter or a
// selection changes what else is on screen. Hue runs out long before threads
// do, so identity rides on two channels: after a full turn of the palette the
// same hue returns in a different stroke.

// Distinct hues, none in the indigo band reserved for the app's accent.
export const LANE_PALETTE = [
  "hsl(145deg 55% 45%)", // green
  "hsl(35deg 85% 50%)", // amber
  "hsl(330deg 70% 55%)", // pink
  "hsl(178deg 55% 40%)", // teal
  "hsl(5deg 72% 56%)", // red
  "hsl(90deg 48% 43%)", // lime
  "hsl(288deg 45% 55%)", // violet
  "hsl(198deg 70% 46%)", // cyan
  "hsl(20deg 45% 42%)", // russet
  "hsl(160deg 40% 62%)", // mint
  "hsl(310deg 55% 40%)", // mulberry
  "hsl(55deg 60% 42%)", // olive
] as const;

/** Solid, dashed, dotted: the second channel once the hues have all been used. */
export const LANE_DASHES = ["", "7 4", "2 4"] as const;

const wrap = (n: number, len: number) => ((n % len) + len) % len;

export function paletteColor(n: number): string {
  return LANE_PALETTE[wrap(n, LANE_PALETTE.length)] ?? LANE_PALETTE[0];
}

/** Which turn of the palette the nth thread falls in: 0 for the first twelve, and so on. */
export function paletteTurn(n: number): number {
  return Math.floor(Math.abs(n) / LANE_PALETTE.length) % LANE_DASHES.length;
}

/** The SVG dash array that goes with the nth colour; "" is solid. */
export function paletteDash(n: number): string {
  return LANE_DASHES[paletteTurn(n)] ?? "";
}

export interface ThreadPaint {
  color: string;
  dash: string;
  turn: number;
}

/**
 * Each thread's paint, from every thread id in the book. Ids are sorted so the
 * answer does not depend on the order a caller happened to list them in.
 */
export function threadPaints(ids: Iterable<string>): Map<string, ThreadPaint> {
  const sorted = [...new Set(ids)].sort();
  return new Map(
    sorted.map((id, n) => [
      id,
      { color: paletteColor(n), dash: paletteDash(n), turn: paletteTurn(n) },
    ]),
  );
}
