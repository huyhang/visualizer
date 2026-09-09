// Draft alignment and prose statistics, independent of DOM and network.

function inlineText(block) {
  const content = block.type === "bullet_list" || block.type === "ordered_list"
    ? (block.content || []).flatMap((item) => item.content || []) : block.content || [];
  return content.map((node) => node.text || (node.type === "hard_break" ? "\n" : "")).join("");
}

export function draftStats(document) {
  const blocks = document.content || [];
  const text = blocks.map(inlineText).join(" ").trim();
  const words = text ? text.split(/\s+/).length : 0;
  const sentences = (text.match(/[^.!?]+[.!?]+|[^.!?]+$/g) || [])
    .map((part) => part.trim()).filter(Boolean);
  return {
    words,
    paragraphs: blocks.filter((block) => block.type === "paragraph").length,
    sentences: sentences.length,
    averageSentenceWords: sentences.length ? Math.round(words / sentences.length) : 0,
  };
}

export function compareDocuments(left, right) {
  const leftBlocks = left.content || [];
  const rightBlocks = right.content || [];
  const leftById = new Map(leftBlocks.map((block) => [block.id, block]));
  const rightIds = new Set(rightBlocks.map((block) => block.id));
  const rows = [];
  let leftCursor = 0;
  for (const rightBlock of rightBlocks) {
    const matching = leftById.get(rightBlock.id);
    if (matching) {
      const target = leftBlocks.indexOf(matching);
      while (leftCursor < target) {
        const removed = leftBlocks[leftCursor++];
        if (!rightIds.has(removed.id)) rows.push(row(removed, null, "removed"));
      }
      leftCursor = target + 1;
      rows.push(row(matching, rightBlock,
        inlineText(matching) === inlineText(rightBlock) ? "same" : "changed"));
    } else {
      rows.push(row(null, rightBlock, "added"));
    }
  }
  while (leftCursor < leftBlocks.length) {
    const removed = leftBlocks[leftCursor++];
    if (!rightIds.has(removed.id)) rows.push(row(removed, null, "removed"));
  }
  return { rows, left: draftStats(left), right: draftStats(right) };
}

function row(left, right, status) {
  return {
    id: (left || right).id,
    status,
    left: left ? inlineText(left) : "",
    right: right ? inlineText(right) : "",
  };
}
