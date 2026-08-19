// Where a goal goes on a graph of scenes. Pure: no DOM, no fetches, no layout.
//
// A goal touches the timeline at exactly one point -- the scene that delivers
// it (`achieved_at`) -- so putting goals on a graph is one question asked of
// every goal: is that scene drawn here? There are three ways for the answer to
// be no, and they are not the same thing:
//
//   no scene yet        the writer has not decided where this lands
//   delivered elsewhere it lands on a scene this view is not showing
//   no longer in the book  the id dangles (a finding already says so)
//
// The tempting simplification is to drop all three on the floor and mark only
// the goals that land somewhere visible. That is what makes a graph lie: a
// thread pursuing four goals and marking one reads as a thread with one goal.
// So this returns the marks *and* what could not be marked, from a single pass,
// and the view is obliged to draw both.
//
// Views differ in what a node covers. On a thread's timeline a node is one
// scene; on the story map a node may be a collapsed band standing for a run of
// them. Callers say which by handing over the coverage, and everything else
// here is the same.

export const NO_SCENE = "no-scene";
export const ELSEWHERE = "elsewhere";
export const MISSING = "missing";

// A node covering exactly itself -- the single-plotline timeline's case.
export const eachAlone = (sceneIds) => [...sceneIds].map((id) => [id, [id]]);

// What each node of a story-map slice stands for. A plain scene stands for
// itself; a folded band stands for every scene inside it, so a goal landing in
// a run is marked on the band rather than disappearing with the rows the band
// swallowed. Nodes here are graph-shaped (snake_case), which is what
// `collapseRuns` hands back -- coverage is decided before the layout runs.
export const coverageOf = (nodes) => (nodes || []).map(
  (n) => [n.id, n.is_band ? [...(n.events || [])] : [n.id]],
);

// Which goals the shown threads are pursuing. The map marks *any* goal that
// lands on a shown scene -- a scene paying off a goal is worth seeing whoever
// pursues it -- but the strip is narrower than that on purpose: naming every
// goal in the book that happens not to be on screen would make the strip
// longer the fewer threads you tick, which is exactly backwards.
export const pursuedBy = (lanes) =>
  new Set((lanes || []).flatMap((lane) => lane.goals || []));

// The strip for a slice: the unplaced goals the shown threads actually pursue.
export const stripFor = (placed, lanes) => {
  const pursued = pursuedBy(lanes);
  return placed.unplaced.filter((g) => pursued.has(g.id));
};

// `refs` are goal refs as the server sends them: `{id, title, missing,
// achieved_at, achieved_scene}`. `coverage` pairs each drawn node with the
// scenes it stands for.
//
// Returns `{marks, unplaced}` -- a Map from node id to the goals landing on it,
// and the goals that landed nowhere, each with the reason in words. One pass
// and one definition of "placed", so the two cannot disagree.
export function placeGoals(refs, coverage) {
  const nodeOf = sceneToNode(coverage);
  const marks = new Map();
  const missed = [];

  for (const ref of refs || []) {
    if (ref.missing) {
      missed.push(unplacedRef(ref, MISSING));
      continue;
    }
    if (!ref.achieved_at) {
      missed.push(unplacedRef(ref, NO_SCENE));
      continue;
    }
    const node = nodeOf.get(ref.achieved_at);
    if (node === undefined) {
      missed.push(unplacedRef(ref, ELSEWHERE));
      continue;
    }
    if (!marks.has(node)) marks.set(node, []);
    marks.get(node).push(ref);
  }
  return { marks, unplaced: missed };
}

function sceneToNode(coverage) {
  const out = new Map();
  for (const [node, scenes] of coverage) {
    for (const scene of scenes) out.set(scene, node);
  }
  return out;
}

function unplacedRef(ref, reason) {
  return { id: ref.id, title: ref.title, reason, note: note(ref, reason) };
}

// Why a goal is not on the graph, in the words the strip shows. Here rather
// than in the views so a goal reads the same above a thread and above the map,
// and so the phrasing is testable without a browser.
//
// "Delivered at" names the scene rather than the thread: this view is not
// showing that scene, so it does not know whose thread it is on -- and the
// scene, with its date, is the thing that answers "where is it, then?".
function note(ref, reason) {
  if (reason === MISSING) return "no longer in this book";
  if (reason === NO_SCENE) return "no scene yet";
  const scene = ref.achieved_scene;
  if (!scene) return "delivered by a scene that is no longer in the book";
  return scene.when
    ? `delivered at ${scene.title} · ${scene.when}`
    : `delivered at ${scene.title}`;
}

// Whether a set of refs has anything worth a strip at all. A thread whose every
// goal lands on it needs no "not landed here" band, and drawing an empty one
// would be chrome saying nothing.
export const anyUnplaced = (placed) => placed.unplaced.length > 0;
