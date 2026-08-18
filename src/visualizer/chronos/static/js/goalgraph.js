// Draws the dependency diagram from `goallayout.js`'s coordinates.
//
// Split from the layout for the reason `storygraph.js` is split from
// `layout.js`: where things go is arithmetic worth testing, and what they look
// like is not. This module owns only the second half.
//
// It is built the same way the story map is, and for the same reason: **edges
// in one SVG layer, node boxes as absolutely-positioned HTML on top of it.**
// SVG text neither wraps nor clips, so a goal called "See the Seal pressed to
// the charter" runs straight over the box beside it, and the only defence is
// guessing how many characters fit — a guess that is wrong in the other theme's
// font, wrong at the other font-scale setting, and wrong for a name full of
// capitals. HTML text is clipped by the box that holds it, at any size, by CSS
// that already exists.
//
// Direction is the whole message: an edge runs from a prerequisite *down* to the
// goal that needs it, so everything above a goal must happen before it. The
// arrowhead says which way to read it; the layout guarantees there is no other
// way to read it, because a goal is always drawn below what it rests on. Both
// the line and its head come from `goallayout.js` as plain coordinates, so the
// geometry is tested and this module only paints it.

import { el, svgEl } from "./dom.js";
import { layoutGoals } from "./goallayout.js";

// The reader's text size relative to the default, so the boxes grow with the
// words in them (see `layoutGoals`). Read at draw time rather than stored: the
// font toggle can be pressed at any moment, and the view redraws when it is.
const textScale = () =>
  (parseFloat(getComputedStyle(document.documentElement).fontSize) || 16) / 16;

export function drawGoalGraph(goals, { selected = null, onPick } = {}) {
  const { nodes, edges, width, height } = layoutGoals(goals, { scale: textScale() });
  const byId = new Map(goals.map((g) => [g.id, g]));

  const svg = svgEl("svg", {
    class: "goal-edges",
    viewBox: `0 0 ${width} ${height}`,
    width, height,
    "aria-hidden": "true",
  });

  for (const edge of edges) {
    // Line and head are two siblings carrying the same class, so highlighting
    // an edge highlights its arrow by construction. The alternative — an SVG
    // `marker` — is drawn out of `defs` and inherits nothing from the path
    // that references it, so it took a second marker to colour a lit edge and
    // the two could drift apart. It also depends on `url(#id)` resolving
    // against the document base, which is the usual reason an arrowhead
    // silently disappears on a page served under a route.
    const lit = touches(edge, selected) ? " is-lit" : "";
    svg.appendChild(svgEl("path", { class: `goal-edge${lit}`, d: edge.path }));
    svg.appendChild(svgEl("polygon", { class: `goal-arrowhead${lit}`, points: edge.arrow }));
  }

  const boxes = el("div", { class: "goal-nodes" },
    nodes.map((node) => nodeBox(node, byId.get(node.id), selected, onPick)));

  return el("div", {
    class: "goal-canvas",
    style: `width:${width}px;height:${height}px`,
    role: "group",
    "aria-label": "Goal dependencies, prerequisites above the goals that need them",
  }, [svg, boxes]);
}

const touches = (edge, selected) =>
  selected != null && (edge.from === selected || edge.to === selected);

function nodeBox(node, goal, selected, onPick) {
  const state = (goal.status || {}).state || "open";
  const name = goal.name || goal.id;
  return el("button", {
    class: `goal-node is-${state}${goal.id === selected ? " is-selected" : ""}`,
    type: "button",
    // The full name, for a box that had to clip it.
    title: name,
    dataset: { goal: goal.id },
    style: `left:${node.x}px;top:${node.y}px;width:${node.width}px;height:${node.height}px`,
    onclick: () => onPick && onPick(goal.id),
  }, [
    el("span", { class: "goal-label", text: name }),
    el("span", { class: "goal-sub", text: subtitle(goal, state) }),
  ]);
}

// One line under the name saying where the goal stands. The scene it lands on
// when it has one, because that is the fact a writer is looking for; the state
// itself otherwise, since "open" is only interesting when there is no scene.
function subtitle(goal, state) {
  if (state === "conflicted") return "needs attention";
  if (goal.achieved_scene) return goal.achieved_scene.title;
  return "no scene yet";
}
