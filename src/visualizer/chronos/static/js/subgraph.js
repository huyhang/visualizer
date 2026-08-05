// Pure graph filtering: given the whole book's story graph and a focused
// plotline, keep only the threads that actually *interact* with it. No DOM, no
// fetches -- it takes the /graph payload and returns a smaller payload of the
// same shape, so the same layout/render code draws either one (the full map is
// just this step skipped).
//
// "Connected" = shares at least one **non-terminus** event with the focus.
// Because every plotline must end at the book's terminus, the terminus is a
// universal join: counting it would make *every* thread "connected" and collapse
// this view into the whole map. So it is excluded from the test (but still drawn,
// as the shared endpoint of whatever threads are shown). When a book has no
// terminus yet, there is no universal join and any shared event connects.

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

// The focus plotline plus everything it meets, as a graph payload of the same
// shape (nodes / edges / plotlines / terminus) narrowed to those threads, with
// `focus` recorded so the renderer can emphasise the chosen thread.
export function connectedTo(graph, focusId) {
  const included = connectedIds(graph, focusId);
  const lanes = (graph.plotlines || []).filter((p) => included.has(p.id));

  const nodeIds = new Set();
  lanes.forEach((p) => p.effective_events.forEach((e) => nodeIds.add(e)));

  const nodes = (graph.nodes || []).filter((n) => nodeIds.has(n.id));
  const edges = (graph.edges || [])
    .filter((e) => e.plotlines.some((p) => included.has(p)))
    .map((e) => ({ ...e, plotlines: e.plotlines.filter((p) => included.has(p)) }));

  return {
    nodes,
    edges,
    plotlines: lanes,
    terminus: nodeIds.has(graph.terminus) ? graph.terminus : null,
    focus: focusId,
  };
}
