// The drawing half of the story map: a laid-out model in, DOM out. Nothing here
// fetches, routes or decides what is shown -- subgraph.js chooses the threads,
// collapse.js chooses the density, layout.js places everything, and storymap.js
// owns the state and hands the result here.
//
// Rendering is a hybrid: one <svg> holds the lanes, node dots and the curved
// edges (which span rows, so they can't be per-row); the event titles and times
// ride alongside as absolutely-positioned HTML, aligned to each node's y, so the
// text and role badges stay crisp and reuse the app's chip/badge styles.
//
// The whole drawing sits in a horizontally scrollable pane. Rows are positioned
// at a computed y but wrap their content, so once the lane gutter squeezes the
// titles past `TEXT_MIN` the rows would overlap rather than merely look cramped
// -- the pane scrolls instead.

import { el, svgEl } from "./dom.js";
import { goalMark, overflowRow } from "./goalcard.js";
import { geometry } from "./layout.js";

// Hue runs out before threads do, so identity rides on colour *and* stroke (see
// layout.paletteDash). Every mark that stands for a thread has to show both, and
// has to tell the strokes apart from each other -- lumping them together as
// "dashed" would make the 13th thread and the 25th identical again, which is the
// collision the second channel exists to prevent.
const STROKE_MARK = { "7 4": " is-dashed", "2 4": " is-dotted" };
const strokeMark = (dash) => STROKE_MARK[dash] || "";

// A thread's colour and stroke, as one small mark. Shared by the picker (so a
// swatch a writer clicks is exactly the lane it turns on) and by every row.
function threadMark(cls, { color, dash }) {
  const mark = strokeMark(dash);
  return el("span", {
    class: cls + mark,
    // Hollow and outlined once a stroke is in play, so the ring shows the
    // pattern; the inline colour beats the stylesheet's `currentColor`.
    style: mark ? `border-color:${color}` : `background:${color}`,
  });
}

export const swatch = (lane) => threadMark("sg-swatch", lane);

// How far from the node a thread starts to turn, before the lane distance is
// added in. Threads reaching further across turn earlier and sweep wider, so
// several joining one node nest instead of crossing.
const TURN = 18;

// A thread keeps its own column for the whole descent and turns *once* — right
// at the node it joins, or immediately after the node it leaves.
//
// The obvious shape, a symmetric S with both control points at the vertical
// midpoint, is wrong here in a way that only shows up on a real book: it reaches
// the target's column halfway up, so a thread joining a lane that already has a
// line running down it lands *on top of that line* for the rest of the way. Two
// threads then read as one. Turning late keeps every thread in a column of its
// own until the moment it actually merges, which is also how the lanes read.
function edgeShape(e) {
  if (e.x1 === e.x2) return `M ${e.x1} ${e.y1} L ${e.x2} ${e.y2}`;
  const span = Math.abs(e.y2 - e.y1);
  const turn = Math.min(span, TURN + Math.abs(e.x2 - e.x1) * 0.5);
  // A quadratic whose control point is the corner itself draws the rounded
  // right-angle we want: it leaves one way and arrives the other.
  return e.x2 < e.x1
    // joining a thread to the left: hold this column, then turn in at the end
    ? `M ${e.x1} ${e.y1} V ${e.y2 - turn} Q ${e.x1} ${e.y2}, ${e.x2} ${e.y2}`
    // departing to the right: turn out at once, then hold the new column
    : `M ${e.x1} ${e.y1} Q ${e.x2} ${e.y1}, ${e.x2} ${e.y1 + turn} V ${e.y2}`;
}

function edgePath(e) {
  const path = svgEl("path", {
    class: "sg-edge" + (e.isFocus ? " is-focus" : ""),
    d: edgeShape(e),
    style: `stroke:${e.color}`,
  });
  if (e.dash) path.setAttribute("stroke-dasharray", e.dash);
  return path;
}

function nodeDot(n) {
  const g = svgEl("g", { class: "sg-node" });
  // A scene that delivers a goal used to gain a third ring here. Two rings are
  // already in play -- focus and terminus -- and a node wearing all three reads
  // as a target rather than a scene. The tick in the row beside it says the same
  // thing in a way that does not compete with the drawing, so the drawing keeps
  // saying only what the drawing is for: where a scene sits in the weave.
  //
  // The thread a writer arrived from keeps its own (stable) colour; an accent
  // ring marks it as "you are here" without recolouring anything.
  if (n.isFocus && !n.isTerminus) {
    g.appendChild(svgEl("circle", {
      class: "sg-focus-ring", cx: n.x, cy: n.y, r: geometry.NODE_R + 3,
    }));
  }
  if (n.isTerminus) {
    g.appendChild(svgEl("circle", {
      class: "sg-ring", cx: n.x, cy: n.y, r: geometry.NODE_R + 3,
      style: `stroke:${n.color}`,
    }));
  }
  // A folded run is drawn hollow: it is a stretch of story, not a scene, and it
  // should not read as one more event on the thread.
  if (n.isBand) {
    g.appendChild(svgEl("circle", {
      class: "sg-dot is-band", cx: n.x, cy: n.y, r: geometry.NODE_R - 1,
      style: `stroke:${n.color}`,
    }));
    return g;
  }
  const cls = "sg-dot"
    + (n.isConvergence ? " is-merge" : "")
    + (n.isDivergence ? " is-split" : "");
  g.appendChild(svgEl("circle", {
    class: cls, cx: n.x, cy: n.y, r: geometry.NODE_R, style: `fill:${n.color}`,
  }));
  return g;
}

// A calendar period band (Year, Month, …), indented by depth -- the same nesting
// the single-plotline timeline shows.
function headerBand(h) {
  return el("div", {
    class: "sg-head " + (h.level === 0 ? "sg-head-top" : "sg-head-sub"),
    style: `top:${h.y}px; padding-left:${h.level * 0.9}rem`,
    text: h.label,
  });
}

// The time on a row, printed once per slot. A merged group says how many scenes
// share the moment, so "at once" is in the text and not only in the layout --
// which a screen reader would never see.
// The time on a row, printed once per slot -- a moment states it for every scene
// standing in it.
function whenLabel(slot) {
  return el("span", { class: "sg-row-when", text: slot.when });
}

// The goals a row delivers. A row is a scene, or a folded band standing for a
// run of them, and either can be where a goal lands -- `goalsAt` was keyed by
// row id after the fold for exactly that reason.
//
// Drawn as its own mark rather than folded into the title, because it is a
// different kind of fact: the title says which scene this is, the mark says
// what the book gets out of it. Clicking opens the goal beside the map.
//
// Under the head and indented to the title, wrapping as a set. Sharing the
// head's line was tried and is worse: a scene can pay off three goals whose
// names are sentences, and squeezing those onto one line spends the scene's own
// title on a row of ellipses. Given a line of their own they simply flow onto a
// second one, and nothing has to be clipped to a guess.
//
// The height that costs is real, and it is not this module's to take. A row is
// absolutely positioned at a y the layout computed, so a row that grows without
// the layout being told lands on top of the row beneath it. `.has-goals` on the
// row is how `storymap.js` finds these and measures them -- that, not this
// markup, is what keeps them from colliding.
//
// A sibling of the row head, never inside it: the head is a `<button>`, and a
// button inside a button is not a thing a browser will honour.
// Two before the rest folds away, one fewer than a thread allows: a map row is
// a line in a dense list, and a map is read for where things sit rather than
// for what each of them is called.
const MARKS_ON_A_MAP_ROW = 2;

function goalChips(n, { goalsAt, onGoal, openMarks, onToggleMarks }) {
  const goals = (goalsAt && goalsAt.get(n.id)) || [];
  if (!goals.length) return null;
  return overflowRow(goals, (ref) => el("button", {
    class: "sg-goal", type: "button",
    title: `${ref.title} \u2014 this scene delivers it`,
    onclick: (e) => { e.stopPropagation(); onGoal(ref.id); },
  }, [
    el("span", { class: "sg-goal-mark", text: goalMark(ref), "aria-hidden": "true" }),
    el("span", { class: "sg-goal-name", text: ref.title }),
  ]), {
    className: "sg-row-goals", max: MARKS_ON_A_MAP_ROW,
    // Controlled: the map rebuilds its rows, so the fold is storymap.js's to
    // remember (see `overflowRow`).
    open: Boolean(openMarks && openMarks.has(n.id)),
    onToggle: onToggleMarks ? () => onToggleMarks(n.id) : undefined,
  });
}

// `.has-goals` on a row that carries marks: the stylesheet indents them by it,
// and storymap.js measures by it.
const marked = (goals) => (goals ? " has-goals" : "");

// A scene's name. The book's terminus is underlined rather than labelled: it is
// one row in the whole map, the note under the diagram says what the underline
// means, and a badge on the busiest row was the thing that wrapped.
function titleSpan(n) {
  if (!n.isTerminus) return el("span", { class: "sg-row-title", text: n.title });
  return el("span", {
    class: "sg-row-title is-terminus",
    title: "The book's terminus — every thread ends here",
    text: n.title,
  });
}

// `+` to open, `−` to close -- the same twisty Akasha's tree browser uses, so a
// writer learns one vocabulary for "there is more inside this" across both apps.
function twisty(open, { title, onToggle } = {}) {
  const mark = el("span", {
    class: "twisty", text: open ? "−" : "+", "aria-hidden": "true",
  });
  if (!onToggle) return mark;
  return el("button", {
    class: "twisty-btn", type: "button", title,
    "aria-expanded": open ? "true" : "false",
    onclick: (e) => { e.stopPropagation(); onToggle(); },
  }, mark);
}

// A thread's mark, beside the scene it belongs to. Every row carries one, not
// only the scenes inside a shared moment -- otherwise a row's thread is only
// legible when it happens to be crowded, which is backwards.
const laneDot = (n) => threadMark("sg-lane-dot", n);

// Merge a group back, or open it out into a row per scene. Offered on the merged
// row and again on the first row of an opened group, so the way in and the way
// back sit in the same place.
function groupToggle(slot, onToggleGroup) {
  const open = !slot.collapsed;
  return twisty(open, {
    title: open
      ? `Hide the ${slot.count} scenes at this moment`
      : `Show the ${slot.count} scenes at this moment`,
    onToggle: () => onToggleGroup(slot.id),
  });
}

// A folded stretch of one thread's solitary scenes. Reads as what it is -- an
// amount of story -- and unfolds into its scenes on click.
function bandRow(slot, n, opts) {
  const goals = goalChips(n, opts);
  return el("div", {
    class: "sg-row is-band" + marked(goals),
    style: `top:${slot.y}px`,
    // Measured like any other row that carries marks, so it needs the id the
    // height is filed under -- the band's own, which is its node id.
    dataset: { event: n.id },
  }, [
    el("button", {
      class: "sg-row-head",
      title: `Unfold these ${n.events.length} scenes`,
      onclick: () => opts.onToggleBand(n),
    }, [
      twisty(false),
      laneDot(n),
      titleSpan(n),
      whenLabel(slot),
    ]),
    // A folded run can be where a goal lands, and folding it must not hide
    // that: the mark says so on the band, and unfolding moves it to the scene.
    goals,
  ].filter(Boolean));
}

// Several scenes at one moment, sharing one row and one y -- so the dots sit at
// the same height on their own threads and nothing implies an order that the
// story does not have. Each scene still opens on its own.
function groupRow(slot, opts) {
  const { expanded, cardFor, onToggleEvent, onToggleBand, onToggleGroup, focusEvent } = opts;
  const scenes = slot.nodes.map((n) => {
    // A moment can hold a folded stretch as easily as a single scene, and the two
    // open onto different things: a band unfolds into its scenes (and leaves the
    // moment), a scene opens its card in place. Wiring both to the same handler
    // asks the API for an event id that was never an event.
    const open = !n.isBand && expanded.has(n.id);
    const toggle = () => (n.isBand ? onToggleBand(n) : onToggleEvent(n));
    const goals = goalChips(n, opts);
    return el("div", {
      class: "sg-group-scene" + (open ? " expanded" : "")
        + (n.isBand ? " is-band" : "") + marked(goals)
        + (n.id === focusEvent ? " focused" : ""),
      dataset: { event: n.id },
      onkeydown: (e) => {
        if (e.key !== "Escape" || !open) return;
        e.stopPropagation();
        onToggleEvent(n);
      },
    }, [
      el("button", {
        class: "sg-row-head",
        title: n.isBand
          ? `Unfold these ${n.events.length} scenes`
          : (open ? "Collapse this scene" : "Show this scene in full"),
        onclick: toggle,
      }, [
        twisty(open),
        laneDot(n),
        titleSpan(n),
      ]),
      goals,
      open ? cardFor(n) : null,
    ].filter(Boolean));
  });

  return el("div", {
    class: "sg-row is-group" + (slot.collapsed ? " collapsed" : ""),
    style: `top:${slot.y}px`,
    dataset: { slot: slot.id },
  }, [
    el("div", { class: "sg-group-bar" }, [
      groupToggle(slot, onToggleGroup),
      el("span", { class: "sg-row-title", text: `${slot.count} at once` }),
      whenLabel(slot),
    ]),
    slot.collapsed ? null : el("div", { class: "sg-group-scenes" }, scenes),
  ].filter(Boolean));
}

// One scene. Minimized to a single legible line by default; clicking enlarges it
// in place into the full card, and every row below moves down to make room.
function eventRow(slot, opts) {
  const { expanded, cardFor, onToggleEvent, onToggleGroup, focusEvent } = opts;
  const n = slot.nodes[0];
  const open = expanded.has(n.id);
  const head = el("button", {
    class: "sg-row-head",
    title: open ? "Collapse this scene" : "Show this scene in full",
    onclick: () => onToggleEvent(n),
  }, [
    twisty(open),
    laneDot(n),
    titleSpan(n),
    whenLabel(slot),
  ]);

  const goals = goalChips(n, opts);
  const row = el("div", {
    class: "sg-row" + (open ? " expanded" : "") + marked(goals)
      + (n.id === focusEvent ? " focused" : ""),
    style: `top:${slot.y}px`,
    dataset: { event: n.id },
    // Esc closes the scene you are reading without reaching for the mouse.
    // Only when it is open, so the key stays free for whatever encloses this view.
    onkeydown: (e) => {
      if (e.key !== "Escape" || !open) return;
      e.stopPropagation();
      onToggleEvent(n);
    },
  }, [head, goals, open ? cardFor(n) : null].filter(Boolean));
  return row;
}

// model: what applyPeriodGrouping returned. Returns the scrollable pane.
export function diagram(model, opts) {
  const wrap = el("div", {
    class: "storygraph",
    style: `height:${model.height}px; min-width:${model.minWidth}px`,
  });
  const svg = svgEl("svg", {
    class: "sg-svg", width: model.width, height: model.height,
    viewBox: `0 0 ${model.width} ${model.height}`,
  });
  model.edges.forEach((e) => svg.appendChild(edgePath(e)));
  model.nodes.forEach((n) => svg.appendChild(nodeDot(n)));
  wrap.appendChild(svg);

  const rows = el("div", { class: "sg-rows", style: `left:${model.width + 12}px` });
  model.headers.forEach((h) => rows.appendChild(headerBand(h)));
  (model.rows || []).forEach((slot) => {
    if (slot.isGroup) return rows.appendChild(groupRow(slot, opts));
    const n = slot.nodes[0];
    return rows.appendChild(
      n.isBand ? bandRow(slot, n, opts) : eventRow(slot, opts),
    );
  });
  wrap.appendChild(rows);
  return el("div", { class: "sg-pane" }, wrap);
}
