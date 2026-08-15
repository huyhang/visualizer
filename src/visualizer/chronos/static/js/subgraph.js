// Pure graph slicing: given the whole book's story graph, keep some of its
// threads. No DOM, no fetches -- it takes the /graph payload and returns a
// smaller payload of the same shape, so the same layout/render code draws either
// one (the whole-book map is just this step given every thread).
//
// Two callers, one rule. The story map narrows to the threads a writer *ticked*;
// the "connected plots" preset narrows to the threads that meet a chosen one and
// then hands the same list to the same narrowing function.
//
// "Connected" = shares at least one **non-terminus** event with the focus.
// Because every plotline must end at the book's terminus, the terminus is a
// universal join: counting it would make *every* thread "connected" and collapse
// that preset into the whole map. So it is excluded from the test (but still
// drawn, as the shared endpoint of whatever threads are shown). When a book has
// no terminus yet, there is no universal join and any shared event connects.

// Narrow a graph to `ids`, dropping every thread, node and edge that no longer
// belongs. `focusId` is recorded (not required to be in `ids`) so the renderer
// can emphasise a thread the writer arrived from.
export function restrictTo(graph, ids, focusId = null) {
  const included = ids instanceof Set ? ids : new Set(ids || []);
  const lanes = (graph.plotlines || []).filter((p) => included.has(p.id));

  const nodeIds = new Set();
  lanes.forEach((p) => (p.effective_events || []).forEach((e) => nodeIds.add(e)));

  const nodes = (graph.nodes || []).filter((n) => nodeIds.has(n.id));
  const edges = (graph.edges || [])
    // Both endpoints have to survive, not just the tag: an edge tagged with a
    // kept thread but reaching a dropped one would dangle.
    .filter((e) => nodeIds.has(e.from) && nodeIds.has(e.to)
      && e.plotlines.some((p) => included.has(p)))
    .map((e) => ({ ...e, plotlines: e.plotlines.filter((p) => included.has(p)) }));

  return {
    nodes,
    edges,
    plotlines: lanes,
    terminus: nodeIds.has(graph.terminus) ? graph.terminus : null,
    focus: focusId,
  };
}

// The set of plotline ids that meet `focusId` somewhere other than the terminus.
export function connectedIds(graph, focusId) {
  const lanes = graph.plotlines || [];
  const focus = lanes.find((p) => p.id === focusId);
  const ids = new Set(focus ? [focusId] : []);
  if (!focus) return ids;

  const terminus = graph.terminus;
  const focusEvents = new Set(focus.effective_events);
  const meets = (lane) => lane.effective_events.some(
    (e) => e !== terminus && focusEvents.has(e),
  );
  for (const lane of lanes) {
    if (lane.id !== focusId && meets(lane)) ids.add(lane.id);
  }
  return ids;
}

// The focus plotline plus everything it meets.
export function connectedTo(graph, focusId) {
  return restrictTo(graph, connectedIds(graph, focusId), focusId);
}
