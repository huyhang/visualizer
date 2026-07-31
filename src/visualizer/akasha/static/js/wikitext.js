// Pure wikitext -> sanitized HTML renderer for the MediaWiki-style subset:
//   '''bold'''  ''italic''  == heading ==  * list item  [[link]] / [[link|label]]
// Everything is HTML-escaped first, so only the tags we emit reach the DOM.

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

export function renderWikitext(text) {
  const lines = String(text || "").split(/\r?\n/);
  const html = [];
  let list = null;
  const flushList = () => { if (list) { html.push(`<ul>${list.join("")}</ul>`); list = null; } };

  for (const raw of lines) {
    const line = raw.trimEnd();
    const heading = line.match(/^(={2,6})\s*(.*?)\s*=*\s*$/);
    if (/^\*\s+/.test(line)) {
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
export async function renderInto(container, text, { scope, resolveTarget, parseTarget, onNavigate }) {
  container.innerHTML = renderWikitext(text);
  const anchors = Array.from(container.querySelectorAll("a.wikilink"));
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
