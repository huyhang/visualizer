// Tiny DOM helpers shared across modules (mirrors akasha's). Everything builds
// via textContent / createElement -- never innerHTML with untrusted data.

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

export function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null) continue;
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else if (k === "html") node.innerHTML = v; // caller guarantees safety
    else if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2), v);
    else if (k === "dataset") Object.assign(node.dataset, v);
    else node.setAttribute(k, v);
  }
  for (const child of [].concat(children)) {
    if (child == null) continue;
    node.appendChild(typeof child === "string" ? document.createTextNode(child) : child);
  }
  return node;
}

export function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); }

// `slugify` used to live here. It now lives in ./shared/slug.js, because akasha
// derives article ids the same way and the two copies drifted.

// SVG sibling of el(): builds elements in the SVG namespace (createElement makes
// inert HTML nodes for <svg>/<path>/<circle>…). Same attr/child conventions,
// minus HTML-only shortcuts (no class=/text= special-casing beyond text).
const SVG_NS = "http://www.w3.org/2000/svg";
export function svgEl(tag, attrs = {}, children = []) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null) continue;
    if (k === "text") node.textContent = v;
    else if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v);
  }
  for (const child of [].concat(children)) {
    if (child == null) continue;
    node.appendChild(typeof child === "string" ? document.createTextNode(child) : child);
  }
  return node;
}

// Prose clamped to a couple of lines, with a toggle that reveals the rest.
//
// Cards are laid out in a grid, so unbounded prose in one of them drags a whole
// row taller and the shelf stops reading as a shelf. Clamping fixes that and
// introduces a worse problem: text that is silently cut off, with nothing on
// screen to say there is more of it. Hence the toggle.
//
// It appears only when the text *actually* overflows, which cannot be known
// from the string — it depends on the rendered width and the font scale. So the
// measurement happens after layout, on the next frame, and a note that happens
// to fit gains no control at all.
export function expandableText(text, { class: className = "" } = {}) {
  const body = el("p", { class: `expandable-text ${className}`.trim(), text });
  const toggle = el("button", {
    class: "expand-toggle", type: "button", text: "Show more", hidden: "",
    onclick: () => {
      const open = body.classList.toggle("expanded");
      toggle.textContent = open ? "Show less" : "Show more";
    },
  });
  // scrollHeight exceeds clientHeight exactly when the clamp is hiding a line.
  // Never while expanded: nothing is being hidden then, and the answer would be
  // "no overflow" — which would take away the control that got you here.
  const measure = () => {
    if (!body.classList.contains("expanded")) {
      toggle.hidden = body.scrollHeight <= body.clientHeight;
    }
  };
  requestAnimationFrame(measure);
  // Re-measured, not measured once: the same words wrap to two lines in a wide
  // card and four in a narrow one, and this app has a font-size toggle. A
  // reflow changes the clamped element's own box either way — its width when
  // the column resizes, its height when the line-height does — so watching it
  // covers both.
  if (typeof ResizeObserver === "function") new ResizeObserver(measure).observe(body);
  return el("div", { class: "expandable" }, [body, toggle]);
}

// One labelled row of a form: the label, the control, and an optional line of
// guidance under it. Every editor in this app is built out of these — the book
// form, the scene form, both calendar forms and the goal form — and each of
// them used to carry its own identical copy. One definition, so a change to how
// a field reads is a change everywhere rather than in four places and a miss.
export function field(label, control, hint) {
  return el("div", { class: "field" }, [
    el("label", { class: "field-label", text: label }),
    control,
    hint ? el("p", { class: "field-hint muted", text: hint }) : null,
  ]);
}

let toastTimer = null;
export function toast(message, isError = false) {
  const node = $("#toast");
  node.textContent = message;
  node.className = "toast" + (isError ? " err" : "");
  node.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { node.hidden = true; }, 3200);
}
