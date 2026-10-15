// What the timeline's cursor says as it moves, and how it keeps saying it.
// Ported from the classic page's cursorlabel.js: policy, not DOM -- a cache, a
// single-flight bound and a rate floor -- handed a `formatTick` and calling
// back with the text that should be on screen.
//
// The rule it keeps: the label never changes notation while it moves. Only the
// server knows what a tick is called, so the reading under a moving cursor
// cannot always be current -- but it can always be a *date*, a moment stale,
// never "Tick 4821". A notation that flips twice a second cannot be read.

const MIN_GAP = 80;

export interface TickLabels {
  cursorAt: (tick: number) => void;
  stop: () => void;
}

export interface TickLabelOptions {
  formatTick: (tick: number) => Promise<string | null | undefined>;
  /** What is already known, as [tick, label] pairs: every scene dates its own two ticks. */
  seeded?: [number, string][];
  onLabel?: (text: string) => void;
  /** The least time between two lookups, in ms. */
  minGap?: number;
  sleep?: (ms: number) => Promise<void>;
  now?: () => number;
}

const realSleep = (ms: number) => new Promise<void>((resume) => setTimeout(resume, ms));

export function tickLabels({
  formatTick,
  seeded = [],
  onLabel = () => {},
  minGap = MIN_GAP,
  sleep = realSleep,
  now = Date.now,
}: TickLabelOptions): TickLabels {
  const labels = new Map(seeded);
  let shown: string | null = null;
  let at: number | null = null;
  let pending: number | null = null;
  let asking = false;
  let lastAsk = -Infinity;
  let stopped = false;

  function publish(text: string | null | undefined) {
    if (!text || text === shown) return;
    shown = text;
    onLabel(text);
  }

  // A known tick is published at once; an unknown one leaves the last date
  // standing and is asked for. The bare tick shows only on a label that has
  // never had a date at all, where the number really is the best reading.
  function cursorAt(tick: number) {
    at = tick;
    const known = labels.get(tick);
    if (known) {
      publish(known);
      return;
    }
    if (!labels.size) publish(`Tick ${tick}`);
    void ask(tick);
  }

  // One request in flight, re-aimed at wherever the cursor has reached by the
  // time the last one lands, and never two closer together than `minGap`:
  // the first bound stops a slow server queueing a scroll's worth of requests,
  // the second stops a fast one being asked hundreds of times a gesture.
  async function ask(tick: number) {
    pending = tick;
    if (asking) return;
    asking = true;
    try {
      while (pending !== null && !stopped) {
        const want: number = pending;
        pending = null;
        if (labels.has(want)) continue;
        const idle = minGap - (now() - lastAsk);
        if (idle > 0) await sleep(idle);
        if (stopped) break;
        // The cursor has likely moved during that pause; spend the request there.
        if (pending !== null && pending !== want) continue;
        pending = null;
        lastAsk = now();
        let formatted: string | null | undefined = null;
        try {
          formatted = await formatTick(want);
        } catch {
          // The date on screen stands; the next move asks again.
        }
        if (stopped) break;
        if (!formatted) continue;
        labels.set(want, formatted);
        // An answer for a tick the cursor has left is worth keeping, not showing.
        if (want === at) publish(formatted);
      }
    } finally {
      asking = false;
    }
  }

  return {
    cursorAt,
    // Nothing still in flight may write to a view that has been torn down.
    stop: () => {
      stopped = true;
    },
  };
}
