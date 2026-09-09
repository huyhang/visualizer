// Structured rich text <-> editable DOM. Stored prose remains the source of
// truth; contenteditable is only a view and never leaks arbitrary HTML to the API.

const MARK_TAGS = { em: "em", strong: "strong", strike: "del", code: "code" };
const TAG_MARKS = { EM: "em", I: "em", STRONG: "strong", B: "strong", DEL: "strike", S: "strike", CODE: "code" };
const MARK_ORDER = ["em", "strong", "strike", "code"];
const HEADINGS = { 1: "h2", 2: "h3", 3: "h4" };
const LEVELS = { H1: 1, H2: 1, H3: 2, H4: 3 };

function safeHref(value) {
  if (!value || value.startsWith("//")) return null;
  if (value.startsWith("/")) return value;
  try {
    const parsed = new URL(value);
    return ["http:", "https:"].includes(parsed.protocol) ? value : null;
  } catch (_error) {
    return null;
  }
}

function attrs(node, values) {
  for (const [name, value] of Object.entries(values)) node.setAttribute(name, value);
  return node;
}

function renderInline(owner, value) {
  if (value.type === "hard_break") return owner.createElement("br");
  if (value.type === "mention" || value.type === "article_link") {
    const node = attrs(owner.createElement("span"), {
      class: "entity-mention",
      "data-entity-type": value.type,
      "data-database": value.ref.database,
      "data-collection": value.ref.collection,
      "data-entity-id": value.ref.id,
      contenteditable: "false",
    });
    node.textContent = value.text;
    return node;
  }
  if (value.type === "link") {
    const node = attrs(owner.createElement("a"), { href: value.href });
    node.textContent = value.text;
    return node;
  }
  let node = owner.createTextNode(value.text);
  for (const mark of value.marks || []) {
    const wrapper = owner.createElement(MARK_TAGS[mark.type]);
    wrapper.appendChild(node);
    node = wrapper;
  }
  return node;
}

function appendInline(owner, parent, content) {
  for (const value of content || []) parent.appendChild(renderInline(owner, value));
  if (!parent.childNodes.length) parent.appendChild(owner.createElement("br"));
}

function renderBlock(owner, block) {
  const list = block.type === "bullet_list" || block.type === "ordered_list";
  const tag = list ? (block.type === "bullet_list" ? "ul" : "ol")
    : block.type === "heading" ? HEADINGS[block.level] : "p";
  const node = attrs(owner.createElement(tag), { "data-block-id": block.id });
  if (list) {
    for (const item of block.content || []) {
      const li = owner.createElement("li");
      appendInline(owner, li, item.content);
      node.appendChild(li);
    }
  } else {
    appendInline(owner, node, block.content);
  }
  return node;
}

export function renderEditorDocument(document, root) {
  const owner = root.ownerDocument;
  root.replaceChildren(...(document.content || []).map((block) => renderBlock(owner, block)));
  if (!root.childNodes.length) {
    root.appendChild(renderBlock(owner, { type: "paragraph", id: newBlockId(), content: [] }));
  }
}

const sameNode = (left, right) => {
  const withoutText = (value) => Object.fromEntries(
    Object.entries(value).filter(([key]) => key !== "text"),
  );
  return JSON.stringify(withoutText(left)) === JSON.stringify(withoutText(right));
};

function compact(nodes) {
  const result = [];
  for (const node of nodes) {
    if (node.type !== "hard_break" && !node.text) continue;
    const previous = result[result.length - 1];
    if (previous && "text" in node && sameNode(previous, node)) previous.text += node.text;
    else result.push(node);
  }
  return result;
}

function inlineNodes(node, context = {}) {
  if (node.nodeType === 3) {
    if (!node.nodeValue) return [];
    if (context.entity) {
      return [{ type: context.entity.type, ref: context.entity.ref, text: node.nodeValue }];
    }
    if (context.href) return [{ type: "link", href: context.href, text: node.nodeValue }];
    const value = { type: "text", text: node.nodeValue };
    if (context.marks && context.marks.size) {
      value.marks = MARK_ORDER.filter((mark) => context.marks.has(mark)).map((type) => ({ type }));
    }
    return [value];
  }
  if (node.nodeType !== 1) return [];
  if (node.tagName === "BR") return [{ type: "hard_break" }];
  const next = { ...context, marks: new Set(context.marks || []) };
  const mark = TAG_MARKS[node.tagName];
  if (mark) next.marks.add(mark);
  if (node.tagName === "A") next.href = safeHref(node.getAttribute("href"));
  if (node.matches("[data-entity-id]")) {
    next.entity = {
      type: node.dataset.entityType || "mention",
      ref: {
        database: node.dataset.database,
        collection: node.dataset.collection,
        id: node.dataset.entityId,
      },
    };
  }
  return compact([...node.childNodes].flatMap((child) => inlineNodes(child, next)));
}

function blockId(node, idFactory) {
  const held = node.nodeType === 1 && node.dataset.blockId;
  const id = held || idFactory();
  if (node.nodeType === 1) node.dataset.blockId = id;
  return id;
}

function asBlock(node, idFactory) {
  if (node.nodeType === 3) {
    return node.nodeValue.trim()
      ? { type: "paragraph", id: idFactory(), content: inlineNodes(node) } : null;
  }
  if (node.nodeType !== 1) return null;
  const id = blockId(node, idFactory);
  if (node.tagName === "UL" || node.tagName === "OL") {
    return {
      type: node.tagName === "UL" ? "bullet_list" : "ordered_list",
      id,
      content: [...node.children].filter((child) => child.tagName === "LI").map((item) => ({
        type: "list_item", content: compact(inlineNodes(item)),
      })),
    };
  }
  if (LEVELS[node.tagName]) {
    return { type: "heading", id, level: LEVELS[node.tagName], content: compact(inlineNodes(node)) };
  }
  return { type: "paragraph", id, content: compact(inlineNodes(node)) };
}

export function newBlockId() {
  if (globalThis.crypto && typeof globalThis.crypto.randomUUID === "function") {
    return `p-${globalThis.crypto.randomUUID()}`;
  }
  return `p-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}

export function documentFromEditor(root, idFactory = newBlockId) {
  return {
    version: 1,
    type: "doc",
    content: [...root.childNodes].map((node) => asBlock(node, idFactory)).filter(Boolean),
  };
}

export function selectedProse(root, selection) {
  if (!selection || selection.rangeCount !== 1 || selection.isCollapsed) return null;
  const range = selection.getRangeAt(0);
  if (!root.contains(range.commonAncestorContainer)) return null;
  const text = selection.toString().replace(/\s+/g, " ").trim();
  if (!text || text.length > 200) return null;
  const element = range.commonAncestorContainer.nodeType === 1
    ? range.commonAncestorContainer : range.commonAncestorContainer.parentElement;
  const block = element && element.closest("[data-block-id]");
  const sameBlock = block && block.contains(range.startContainer) && block.contains(range.endContainer);
  return { text, range: range.cloneRange(), block: sameBlock ? block.dataset.blockId : null };
}

export function linkMention(selection, entity) {
  if (!selection || !selection.block || !selection.range) return false;
  const range = selection.range;
  const owner = range.startContainer.ownerDocument;
  const label = range.toString();
  if (!label.trim()) return false;
  const mention = attrs(owner.createElement("span"), {
    class: "entity-mention",
    "data-entity-type": "mention",
    "data-database": entity.database,
    "data-collection": entity.collection,
    "data-entity-id": entity.id,
    contenteditable: "false",
  });
  mention.textContent = label;
  range.deleteContents();
  range.insertNode(mention);
  range.setStartAfter(mention);
  range.collapse(true);
  const browserSelection = owner.defaultView && owner.defaultView.getSelection();
  if (browserSelection) {
    browserSelection.removeAllRanges();
    browserSelection.addRange(range);
  }
  return true;
}

export function wordCount(document) {
  const text = (document.content || []).flatMap((block) => {
    const nodes = block.type === "bullet_list" || block.type === "ordered_list"
      ? (block.content || []).flatMap((item) => item.content || []) : block.content || [];
    return nodes.map((node) => node.text || "");
  }).join(" ").trim();
  return text ? text.split(/\s+/).length : 0;
}
