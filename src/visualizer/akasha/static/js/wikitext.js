// Pure wikitext -> sanitized HTML renderer for the MediaWiki-style subset:
//   '''bold'''  ''italic''  == heading ==  * list item  [[link]] / [[link|label]]
// Everything is HTML-escaped first, so only the tags we emit reach the DOM.

import { parseImageDirective } from "./image-format.js";

const LINK_RE = /\[\[([^\]]+)\]\]/g;

// Escape only the characters unsafe in HTML *text* content. We deliberately do
// NOT escape quotes here: the wikitext markers are quote characters
// ('''bold''', ''italic''), so escaping them would stop them ever matching. The
// one place a quote matters — the link target attribute — is escaped separately
// in renderInline, so this stays XSS-safe.
function esc(s) {
  return String(s)
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
}

// Inline formatting on an already-escaped line. Links are emitted as anchors
// with a data-target attribute that the reader wires up for navigation.
function renderInline(escaped) {
  let out = escaped.replace(LINK_RE, (_, body) => {
    const pipe = body.indexOf("|");
    const target = (pipe === -1 ? body : body.slice(0, pipe)).trim();
    const label = (pipe === -1 ? body : body.slice(pipe + 1)).trim();
    // `escaped` already ran through esc() (&, <, > handled), so target/label are
    // safe as text; escape the attribute value's quotes for the data-target.
    const safeTarget = target.replaceAll('"', "&quot;");
    return `<a class="wikilink" href="#" data-target="${safeTarget}">${label}</a>`;
  });
  out = out.replace(/'''(.+?)'''/g, "<strong>$1</strong>");
  out = out.replace(/''(.+?)''/g, "<em>$1</em>");
  return out;
}

function renderImage(placement) {
  const caption = esc(placement.caption);
  const figcaption = caption ? `<figcaption>${caption}</figcaption>` : "";
  return `<figure class="article-image align-${placement.align}" style="--image-width:${placement.width}%">`
    + `<button type="button" class="article-image-open" data-media-id="${placement.media_id}" aria-label="Open full-size image">`
    + `<span class="image-placeholder">Loading image…</span></button>${figcaption}</figure>`;
}

export function createImageFigure(placement, className = "") {
  const figure = document.createElement("figure");
  figure.className = `article-image align-${placement.align}${className ? " " + className : ""}`;
  figure.style.setProperty("--image-width", `${placement.width}%`);
  const button = document.createElement("button");
  button.type = "button";
  button.className = "article-image-open";
  button.dataset.mediaId = placement.media_id;
  button.setAttribute("aria-label", "Open full-size image");
  const placeholder = document.createElement("span");
  placeholder.className = "image-placeholder";
  placeholder.textContent = "Loading image…";
  button.appendChild(placeholder);
  figure.appendChild(button);
  if (placement.caption) {
    const caption = document.createElement("figcaption");
    caption.textContent = placement.caption;
    figure.appendChild(caption);
  }
  return figure;
}

export function renderWikitext(text) {
  const lines = String(text || "").split(/\r?\n/);
  const html = [];
  let list = null;
  const flushList = () => { if (list) { html.push(`<ul>${list.join("")}</ul>`); list = null; } };

  for (const raw of lines) {
    const line = raw.trimEnd();
    const heading = line.match(/^(={2,6})\s*(.*?)\s*=*\s*$/);
    const image = parseImageDirective(line);
    if (image) {
      flushList();
      html.push(renderImage(image));
    } else if (/^\*\s+/.test(line)) {
      list = list || [];
      list.push(`<li>${renderInline(esc(line.replace(/^\*\s+/, "")))}</li>`);
    } else if (heading) {
      flushList();
      const level = Math.min(heading[1].length, 6); // == -> h2, === -> h3, ...
      html.push(`<h${level}>${renderInline(esc(heading[2]))}</h${level}>`);
    } else if (line.trim() === "") {
      flushList();
    } else {
      flushList();
      html.push(`<p>${renderInline(esc(line))}</p>`);
    }
  }
  flushList();
  return html.join("");
}

// Render into a container and wire link chips: resolve titles/existence and
// call onNavigate(target) on click.
export async function hydrateImages(container, { resolveMedia, onOpenImage }) {
  if (!resolveMedia) return;
  const figures = Array.from(container.querySelectorAll("figure.article-image"));
  await Promise.all(figures.map(async (figure) => {
    const button = figure.querySelector(".article-image-open");
    try {
      const media = await resolveMedia(button.dataset.mediaId);
      const image = document.createElement("img");
      image.src = media.display_url;
      image.alt = media.alt;
      image.loading = "lazy";
      image.decoding = "async";
      button.textContent = "";
      button.appendChild(image);
      button.addEventListener("click", () => {
        if (onOpenImage) onOpenImage(media, figure.querySelector("figcaption")?.textContent || "");
      });
    } catch (error) {
      button.disabled = true;
      button.textContent = "Image unavailable";
      figure.classList.add("image-missing");
    }
  }));
}

export async function renderInto(container, text, options) {
  const { scope, resolveTarget, parseTarget, onNavigate } = options;
  container.innerHTML = renderWikitext(text);
  const anchors = Array.from(container.querySelectorAll("a.wikilink"));
  if (resolveTarget) {
    await Promise.all(anchors.map(async (a) => {
      const target = parseTarget(a.dataset.target, scope);
      const info = await resolveTarget(target);
      if (!info.exists) a.classList.add("redlink");
      if (!a.textContent.trim() || a.textContent.trim() === a.dataset.target) {
        a.textContent = info.title;
      }
      a.addEventListener("click", (e) => { e.preventDefault(); onNavigate(target, info); });
    }));
  }
  await hydrateImages(container, options);
}
