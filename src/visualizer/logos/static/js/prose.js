// The manuscript's rich text, turned into nodes rather than into markup.
//
// The document arrives as the vocabulary `logos/richtext.py` validates, and
// every branch here is one of its node types. Two properties matter more than
// the shape:
//
//   * nothing is ever concatenated into HTML. Prose becomes text nodes and
//     tags come from a fixed table, so a chapter containing "<script>" is a
//     chapter that reads "<script>".
//   * anything unrecognised throws instead of rendering. The API validates
//     exhaustively, so an unknown node here means a writer newer than this
//     reader -- and guessing at someone's prose is worse than declining to
//     show it and saying so.
//
// The node factory is injected: the page passes a DOM adapter, a test passes a
// plain-object one. That is what lets pytest assert the whole element tree,
// attributes included, without a browser.

const BLOCKS = new Set(["paragraph", "heading", "bullet_list", "ordered_list"]);
const INLINES = new Set(["text", "hard_break", "link", "mention", "article_link"]);
const MARK_TAGS = { em: "em", strong: "strong", strike: "del", code: "code" };
const LIST_TAGS = { bullet_list: "ul", ordered_list: "ol" };
// The open section owns h1, so its document headings start immediately below
// it and the outline a screen reader builds stays in order.
const HEADING_TAGS = { 1: "h2", 2: "h3", 3: "h4" };

export class RenderError extends Error {
  // Without this a subclass reports itself as "Error" in a console or a report,
  // which is the one moment you want it to say which layer gave up.
  name = "RenderError";
}

/**
 * The href to use, or null when there is none worth trusting.
 *
 * The API already restricts stored hrefs to http, https and a site-relative
 * path. This checks again anyway -- it is the last gate before a URL becomes
 * a clickable element, it costs four lines, and it is the difference between
 * "we validate on write" and "a link cannot be a script". Protocol-relative
 * `//host` is rejected too: it passes the server's leading-slash rule while
 * meaning somewhere else entirely.
 */
export function safeHref(value) {
  if (typeof value !== "string") return null;
  if (value.startsWith("//")) return null;
  if (value.startsWith("/")) return value;
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:" ? value : null;
  } catch (_error) {
    return null;
  }
}

export function renderDocument(document, nodes) {
  if (!document || document.type !== "doc" || document.version !== 1) {
    throw new RenderError("Unsupported rich-text document.");
  }
  return nodes.fragment(
    asList(document.content, "Document content").map((b) => renderBlock(b, nodes)),
  );
}

function renderBlock(block, nodes) {
  if (!block || !BLOCKS.has(block.type)) {
    throw new RenderError("Unsupported document block.");
  }
  // The stable block id travels with the node: paragraph-level anchors and
  // annotations are the reason the API mints them in the first place.
  const attrs = {
    "data-block-id": asText(block.id, "Block id"),
    "data-block-type": block.type,
  };
  if (block.type === "heading") return renderHeading(block, attrs, nodes);
  if (LIST_TAGS[block.type]) return renderList(block, attrs, nodes);
  return nodes.element("p", attrs, inlineContent(block, nodes));
}

function renderHeading(block, attrs, nodes) {
  const tag = HEADING_TAGS[block.level];
  if (!tag) throw new RenderError("Unsupported heading level.");
  return nodes.element(tag, attrs, inlineContent(block, nodes));
}

function renderList(block, attrs, nodes) {
  const items = asList(block.content, "List content").map((item) => {
    if (!item || item.type !== "list_item") {
      throw new RenderError("Unsupported list item.");
    }
    return nodes.element("li", {}, inlineContent(item, nodes));
  });
  return nodes.element(LIST_TAGS[block.type], attrs, items);
}

function inlineContent(node, nodes) {
  return asList(node.content || [], "Inline content").map((c) => renderInline(c, nodes));
}

function renderInline(node, nodes) {
  if (!node || !INLINES.has(node.type)) {
    throw new RenderError("Unsupported inline node.");
  }
  if (node.type === "hard_break") return nodes.element("br");
  if (node.type === "text") return renderText(node, nodes);
  // An Akasha mention stays prose in *both* modes. Focused shows nothing from
  // another service, and Full View's one exception is Chronos scenes; a
  // character chip here would quietly make that promise false.
  if (node.type !== "link") return nodes.text(asText(node.text, "Reference text"));
  return renderLink(node, nodes);
}

function renderLink(node, nodes) {
  const label = nodes.text(asText(node.text, "Link text"));
  const href = safeHref(node.href);
  if (!href) return label;
  const external = !href.startsWith("/");
  const attrs = external
    ? { href, target: "_blank", rel: "noopener noreferrer" }
    : { href };
  return nodes.element("a", attrs, [label]);
}

function renderText(node, nodes) {
  return asList(node.marks || [], "Text marks").reduce((rendered, mark) => {
    const tag = mark && MARK_TAGS[mark.type];
    if (!tag) throw new RenderError("Unsupported text mark.");
    return nodes.element(tag, {}, [rendered]);
  }, nodes.text(asText(node.text, "Text node")));
}

function asList(value, where) {
  if (!Array.isArray(value)) throw new RenderError(`${where} must be a list.`);
  return value;
}

function asText(value, where) {
  if (typeof value !== "string") throw new RenderError(`${where} must be text.`);
  return value;
}
