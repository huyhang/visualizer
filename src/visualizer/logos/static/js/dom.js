// The browser side of the node factory `prose.js` takes by injection, plus the
// two helpers the rest of the page builds its own chrome with.
//
// `el` never accepts a string of markup, which is the point: there is no code
// path in this reader that turns manuscript content into HTML, so there is no
// code path to get wrong later.

export function nodeFactory(owner = document) {
  return {
    text(value) {
      return owner.createTextNode(value);
    },
    element(tag, attrs = {}, children = []) {
      const node = owner.createElement(tag);
      for (const [name, value] of Object.entries(attrs)) {
        if (value === null || value === undefined || value === false) continue;
        if (name === "text") node.textContent = value;
        else if (name.startsWith("on")) node.addEventListener(name.slice(2), value);
        else node.setAttribute(name, value === true ? "" : String(value));
      }
      for (const child of children.flat()) {
        if (child !== null && child !== undefined) node.appendChild(child);
      }
      return node;
    },
    fragment(children = []) {
      const fragment = owner.createDocumentFragment();
      for (const child of children.flat()) {
        if (child !== null && child !== undefined) fragment.appendChild(child);
      }
      return fragment;
    },
  };
}

// Keep the adapter importable under Node so its edge cases can be exercised
// without manufacturing a global browser document.
const browser = typeof document === "undefined" ? null : nodeFactory(document);

export function el(tag, attrs = {}, children = []) {
  return browser.element(tag, attrs, children);
}

const SVG_NS = "http://www.w3.org/2000/svg";

/**
 * The same builder for SVG, which needs its own namespace to render at all.
 * Still no markup strings: an icon is a shape, not a blob of HTML.
 */
export function svgEl(tag, attrs = {}, children = []) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [name, value] of Object.entries(attrs)) {
    if (value === null || value === undefined || value === false) continue;
    node.setAttribute(name, value === true ? "" : String(value));
  }
  for (const child of children.flat()) {
    if (child !== null && child !== undefined) node.appendChild(child);
  }
  return node;
}

export function clear(node) {
  while (node.firstChild) node.removeChild(node.firstChild);
  return node;
}

export function fill(node, children) {
  clear(node).appendChild(browser.fragment(children));
  return node;
}
