// Pure helpers about a plotline's scheduling. No DOM, no fetches.

// Whether EVERY event is scheduled (both ticks set). Used only to phrase the
// timeline note; an unscheduled scene has no place on a clock (design §4).
export function allScheduled(events) {
  return events.length > 0 && events.every(
    (e) => e.scheduled && e.start_tick != null && e.end_tick != null,
  );
}

// Coarse-to-fine label components. Chronos now supplies these already split
// (`start_parts`/`end_parts`) straight from the calendar codec, so we never parse
// the display string -- robust to any cycle names, depth, or commas. We fall back
// to splitting the label only if an older response omits the arrays.
const _split = (label) => String(label).split(", ");
const _startParts = (e) => (e.start_parts && e.start_parts.length ? e.start_parts : _split(e.start_label));
const _endParts = (e) =>
  e.end_parts && e.end_parts.length ? e.end_parts : (e.end_label != null ? _split(e.end_label) : null);

// Index of the first component at which two coarse-to-fine lists differ.
function _firstDiff(a, b) {
  let i = 0;
  while (i < a.length && i < b.length && a[i] === b[i]) i++;
  return i;
}

// Group a plotline's events into nested period headers + event rows, driven by
// the calendar itself: every component *coarser* than the finest pair becomes a
// header level, and the finest cycle + clock stay on the event node. So a
// Year/Month/Day calendar nests Year -> Month with "Day, time" on the node; a
// deeper Era/Age/Moon/Span calendar nests three levels; and a bare-tick (no
// calendar) or single-cycle calendar emits no headers (flat). Returns a flat,
// ordered list of items:
//   {type:"header", level, label}
//   {type:"event",  event, label, depth}   // depth = number of header levels
// An event's span end is trimmed of the components it shares with its own start;
// unscheduled scenes read "unscheduled" and sit under the current period.
export function groupByPeriod(events) {
  const items = [];
  let shown = []; // the header components currently in effect
  for (const e of events) {
    if (!e.scheduled || e.start_label == null) {
      items.push({ type: "event", event: e, label: "unscheduled", depth: shown.length });
      continue;
    }
    const parts = _startParts(e);
    const headers = parts.slice(0, -2);     // coarser than the finest (cycle, clock) pair
    let label = parts.slice(-2).join(", "); // finest cycle + clock stay on the node
    const end = _endParts(e);
    if (end && e.end_label !== e.start_label) {
      label += ` → ${end.slice(_firstDiff(parts, end)).join(", ")}`;
    }
    // (Re-)emit any header level from the first that changed down to the deepest.
    for (let i = _firstDiff(shown, headers); i < headers.length; i++) {
      items.push({ type: "header", level: i, label: headers[i] });
    }
    shown = headers;
    items.push({ type: "event", event: e, label, depth: headers.length });
  }
  return items;
}
