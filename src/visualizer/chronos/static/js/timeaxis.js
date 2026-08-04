// Pure helpers about a plotline's scheduling. No DOM, no fetches.

// Whether EVERY event is scheduled (both ticks set). Used only to phrase the
// timeline note; an unscheduled scene has no place on a clock (design §4).
export function allScheduled(events) {
  return events.length > 0 && events.every(
    (e) => e.scheduled && e.start_tick != null && e.end_tick != null,
  );
}
