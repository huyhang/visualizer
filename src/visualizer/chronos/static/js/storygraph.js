// The "Connected plots" view: the focus thread and every plotline that meets it,
// drawn as a branch/merge (git-graph) diagram laid out by time. This module does
// the impure work -- fetch, mount, wire clicks; the *what goes where* is the pure
// subgraph.js + layout.js it drives, so the same drawing serves the whole story
// map later (feed layoutGraph the full graph instead of a connected slice).
//
// Rendering is a hybrid: one <svg> holds the lanes, node dots and the curved
// edges (which span rows, so they can't be per-row); the event titles + times
// ride alongside as absolutely-positioned HTML, aligned to each node's y, so the
// text and role badges stay crisp and reuse the app's chip/badge styles.

import { api } from "./api.js";
import { clear, el, svgEl } from "./dom.js";
import { geometry, layoutGraph, paletteColor } from "./layout.js";
import { connectedTo } from "./subgraph.js";
import { groupByPeriod } from "./timeaxis.js";

const HEADER_H = 30; // vertical room a calendar period band takes

// -- small pieces ------------------------------------------------------------

function breadcrumb(bookTitle, focusTitle, { onBooks, onBook, onTimeline }) {
  return el("nav", { class: "crumbs" }, [
    el("a", { href: "#/", text: "Books", onclick: (e) => { e.preventDefault(); onBooks(); } }),
    el("span", { class: "sep", text: "›" }),
    el("a", { href: "#/", text: bookTitle, onclick: (e) => { e.preventDefault(); onBook(); } }),
    el("span", { class: "sep", text: "›" }),
    el("a", { href: "#/", text: focusTitle, onclick: (e) => { e.preventDefault(); onTimeline(); } }),
    el("span", { class: "sep", text: "›" }),
    el("span", { text: "Connected plots" }),
  ]);
}

// Promote coarse calendar components (Year, Month, …) into period header bands
// and keep only the fine part on each event row -- exactly how the single-plotline
// timeline reads -- by running the shared `groupByPeriod` grouper over the nodes
// in time order. Headers take vertical room, so node/edge y are recomputed from
// the grouped sequence (and edges just span the larger gaps). Returns the drawing
// model: { headers, nodes (with y + compact `when`), edges, width, height }.
function applyPeriodGrouping(layout) {
  const ordered = [...layout.nodes].sort((a, b) => a.y - b.y);
  // Adapter objects in the shape groupByPeriod expects (snake_case + parts).
  const adapters = ordered.map((n) => ({
    scheduled: n.scheduled,
    start_label: n.startLabel,
    end_label: n.endLabel,
    start_parts: n.startParts,
    end_parts: n.endParts,
    _node: n,
  }));

  const headers = [];
  const cy = new Map();   // node id -> centre y
  const when = new Map(); // node id -> compact period label
  let y = geometry.PAD_TOP;
  for (const item of groupByPeriod(adapters)) {
    if (item.type === "header") {
      headers.push({ level: item.level, label: item.label, y });
      y += HEADER_H;
    } else {
      const n = item.event._node;
      cy.set(n.id, y + geometry.ROW_H / 2);
      when.set(n.id, item.label);
      y += geometry.ROW_H;
    }
  }

  const nodes = ordered.map((n) => ({ ...n, y: cy.get(n.id), when: when.get(n.id) }));
  const yOf = new Map(nodes.map((n) => [n.id, n.y]));
  const edges = layout.edges.map((e) => ({ ...e, y1: yOf.get(e.from), y2: yOf.get(e.to) }));
  return { headers, nodes, edges, width: layout.width, height: y + 8 };
}

// A colour swatch + name per thread; clicking another thread re-centres the view
// on it, so the writer can follow a thread through the weave.
function legend(layout, focusId, onPlotline) {
  const chip = (l) => {
    const swatch = el("span", { class: "sg-swatch", style: `background:${l.color}` });
    if (l.id === focusId) {
      return el("span", { class: "sg-legend-chip is-focus", title: "The thread you're viewing" },
        [swatch, el("span", { text: l.title }), el("span", { class: "sg-you", text: "· this thread" })]);
    }
    return el("button", {
      class: "sg-legend-chip", title: `Centre on “${l.title}”`, onclick: () => onPlotline(l.id),
    }, [swatch, el("span", { text: l.title })]);
  };
  return el("div", { class: "sg-legend" }, layout.lanes.map(chip));
}

function edgePath(e) {
  const midY = (e.y1 + e.y2) / 2;
  const d = e.x1 === e.x2
    ? `M ${e.x1} ${e.y1} L ${e.x2} ${e.y2}`
    : `M ${e.x1} ${e.y1} C ${e.x1} ${midY}, ${e.x2} ${midY}, ${e.x2} ${e.y2}`;
  return svgEl("path", { class: "sg-edge" + (e.isFocus ? " is-focus" : ""), d, style: `stroke:${e.color}` });
}

function nodeDot(n) {
  const g = svgEl("g", { class: "sg-node" });
  // The focus thread keeps its own (stable) colour; an accent ring marks it as
  // "you are here" without changing the colour when you re-centre.
  if (n.isFocus && !n.isTerminus) {
    g.appendChild(svgEl("circle", { class: "sg-focus-ring", cx: n.x, cy: n.y, r: geometry.NODE_R + 3 }));
  }
  if (n.isTerminus) {
    g.appendChild(svgEl("circle", {
      class: "sg-ring", cx: n.x, cy: n.y, r: geometry.NODE_R + 3,
      style: `stroke:${n.color}`,
    }));
  }
  const cls = "sg-dot"
    + (n.isConvergence ? " is-merge" : "")
    + (n.isDivergence ? " is-split" : "");
  g.appendChild(svgEl("circle", { class: cls, cx: n.x, cy: n.y, r: geometry.NODE_R, style: `fill:${n.color}` }));
  return g;
}

// A calendar period band (Year, Month, …) in the right column, indented by depth
// -- the same nesting the single-plotline timeline shows.
function headerBand(h) {
  return el("div", {
    class: "sg-head " + (h.level === 0 ? "sg-head-top" : "sg-head-sub"),
    style: `top:${h.y}px; padding-left:${h.level * 0.9}rem`,
    text: h.label,
  });
}

function nodeRow(n, focusEvent, onOpen) {
  const badges = [];
  if (n.isTerminus) badges.push(el("span", { class: "badge terminus", text: "terminus" }));
  else if (n.isConvergence) badges.push(el("span", { class: "badge merge", text: "join" }));
  if (n.isDivergence) badges.push(el("span", { class: "badge split", text: "split" }));

  return el("button", {
    class: "sg-row" + (n.id === focusEvent ? " focused" : ""),
    style: `top:${n.y}px`,
    onclick: () => onOpen(n),
  }, [
    el("span", { class: "sg-row-title", text: n.title }),
    el("span", { class: "sg-row-when", text: n.when }),
    badges.length ? el("div", { class: "chip-row sg-row-badges" }, badges) : null,
  ]);
}

function diagram(model, focusEvent, onOpen) {
  const wrap = el("div", { class: "storygraph", style: `height:${model.height}px` });
  const svg = svgEl("svg", {
    class: "sg-svg", width: model.width, height: model.height,
    viewBox: `0 0 ${model.width} ${model.height}`,
  });
  model.edges.forEach((e) => svg.appendChild(edgePath(e)));
  model.nodes.forEach((n) => svg.appendChild(nodeDot(n)));
  wrap.appendChild(svg);

  const rows = el("div", { class: "sg-rows", style: `left:${model.width + 12}px` });
  model.headers.forEach((h) => rows.appendChild(headerBand(h)));
  model.nodes.forEach((n) => rows.appendChild(nodeRow(n, focusEvent, onOpen)));
  wrap.appendChild(rows);
  return wrap;
}

// -- mount -------------------------------------------------------------------

export async function mountConnected(container, book, plotlineId, deps) {
  const { focusEvent, showEventPeek, onBooks, onBook, onTimeline, onPlotline } = deps;
  clear(container);
  container.appendChild(el("div", { class: "view" },
    el("p", { class: "muted", text: "Loading connections…" })));

  let graph;
  try {
    graph = await api.getGraph(book);
  } catch (e) {
    clear(container);
    container.appendChild(el("div", { class: "view" },
      el("p", { class: "empty", text: "Could not load the story graph." })));
    return;
  }

  let bookMeta = { title: book };
  try { bookMeta = await api.getBook(book); } catch (e) { /* fall back to id */ }

  const focusLane = (graph.plotlines || []).find((p) => p.id === plotlineId);
  const focusTitle = focusLane ? focusLane.title : plotlineId;

  const view = el("div", { class: "view connected-view" });
  view.appendChild(breadcrumb(bookMeta.title || book, focusTitle, { onBooks, onBook, onTimeline }));

  if (!focusLane) {
    view.appendChild(el("p", { class: "empty", text: "That plotline does not exist." }));
    clear(container);
    container.appendChild(view);
    return;
  }

  const sub = connectedTo(graph, plotlineId);
  const others = sub.plotlines.filter((p) => p.id !== plotlineId);

  view.appendChild(el("div", { class: "pl-header" }, [
    el("h1", { class: "view-title", text: focusTitle }),
    el("p", { class: "muted axis-note", text: others.length
      ? `Connected plots — meets ${others.length} other plotline${others.length === 1 ? "" : "s"}. `
        + `Threads run top to bottom in time; the highlighted spine is “${focusTitle}”.`
      : "Connected plots" }),
  ]));

  if (!others.length) {
    view.appendChild(el("p", { class: "empty", text:
      "This thread doesn't meet any other plotline in the story — it runs on its "
      + "own until the shared ending." }));
    clear(container);
    container.appendChild(view);
    return;
  }

  // Stable colours: index each thread by its position in the whole book (the
  // full graph is name-ordered), so a thread's colour is identical across every
  // connected view and never shifts when you re-centre on another thread.
  const bookOrder = (graph.plotlines || []).map((p) => p.id);
  const colorOf = (id) => paletteColor(bookOrder.indexOf(id));

  const layout = layoutGraph(sub, { colorOf });
  const model = applyPeriodGrouping(layout);
  view.appendChild(legend(layout, plotlineId, onPlotline));
  view.appendChild(diagram(model, focusEvent, showEventPeek));
  if (layout.hasUnscheduled) {
    view.appendChild(el("p", { class: "muted axis-note", text:
      "Some scenes have no timing yet; they settle below the scheduled ones." }));
  }

  clear(container);
  container.appendChild(view);

  // If we arrived from a specific event marker, bring it into view.
  if (focusEvent) {
    const row = view.querySelector(".sg-row.focused");
    if (row) row.scrollIntoView({ block: "center" });
  }
}
