// What the lens over the rail says as it moves, and how it keeps saying it.
//
// Split out of scenetimeline.js for the reason timelinelayout.js was: this is
// policy rather than DOM -- a cache, a single-flight bound and a rate floor --
// and none of it is reachable from a test that has to mount a timeline first.
// Nothing here touches an element; it is handed a `formatTick` and calls back
// with the text that should be on screen.
//
// The rule it exists to keep: **the lens never changes notation while it moves.**
// Only the book's calendar knows what a tick is called and only the server holds
// the calendar, so the reading under a moving cursor cannot always be current.
// It can always be a *date*, though -- a slightly stale one for a moment, never
// `Tick 4821` -- and that is the trade made here. A writer scrolling for "some
// evening around the twenty-third" reads the shape of the label as much as its
// value, and a notation that flips twice a second cannot be read at all.

const MIN_GAP = 80;

const sleep = (ms) => new Promise((resume) => { setTimeout(resume, ms); });

/**
 * `formatTick(tick)` resolves to what the book's calendar calls that tick.
 * `seeded` is whatever the caller already knows, as [tick, label] pairs — the
 * timeline payload dates every scene's two ticks, so those cost nothing.
 * `onLabel(text)` is called only when the text on screen should change.
 */
export function tickLabels({
  formatTick, seeded = [], onLabel = () => {}, minGap = MIN_GAP,
} = {}) {
  const labels = new Map(seeded);
  let shown = null;    // the text last handed to `onLabel`
  let at = null;       // where the cursor is
  let pending = null;  // where it has reached since a request went out
  let asking = false;
  let lastAsk = 0;
  let stopped = false;

  function publish(text) {
    if (!text || text === shown) return;
    shown = text;
    onLabel(text);
  }

  // Where the cursor is now. A tick already dated is published at once; one that
  // is not leaves whatever is up there standing, and is asked for. The bare tick
  // is only ever shown by a lens that has never had a date at all — a book whose
  // scenes carry no labels, where the number really is the best reading there is.
  function cursorAt(tick) {
    at = tick;
    const known = labels.get(tick);
    if (known) {
      publish(known);
      return;
    }
    if (!labels.size) publish(`Tick ${tick}`);
    ask(tick);
  }

  // One request in flight, always re-aimed at wherever the cursor has reached by
  // the time the last one lands, and never two closer together than `minGap`.
  // Two bounds rather than one because they cover opposite failures: without the
  // first, a slow answer queues a whole scroll's worth of requests behind it;
  // without the second, a fast one is re-asked the instant it returns, and a
  // gesture that used to cost a request or two costs hundreds. Between them the
  // date keeps up with the hand at a rate a reader can follow and a server will
  // not feel.
  async function ask(tick) {
    pending = tick;
    if (asking) return;
    asking = true;
    try {
      while (pending != null && !stopped) {
        const want = pending;
        pending = null;
        if (labels.has(want)) continue;
        const idle = minGap - (Date.now() - lastAsk);
        if (idle > 0) await sleep(idle);
        if (stopped) break;
        // The cursor has very likely moved during that pause, and where it is
        // now is what the request should be spent on, not where it was.
        if (pending != null && pending !== want) continue;
        pending = null;
        lastAsk = Date.now();
        let formatted = null;
        try {
          formatted = await formatTick(want);
        } catch (e) { /* the date on screen stands; the next move asks again */ }
        if (stopped) break;
        if (!formatted) continue;
        labels.set(want, formatted);
        // Only if the cursor is still there. An answer for a tick it has already
        // scrolled past is worth keeping and not worth showing.
        if (want === at) publish(formatted);
      }
    } finally {
      asking = false;
    }
  }

  // Nothing still in flight may write to a view that has been torn down.
  function stop() {
    stopped = true;
  }

  return { cursorAt, stop };
}
