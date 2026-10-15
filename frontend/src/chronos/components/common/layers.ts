// Which layer a key press belongs to. The workspace listens for a few keys on
// the window -- Escape for the inspector, ⌘K for the palette, ⌘Z in the
// thread editor -- and each must stay out of the way of whatever dialog is
// on top, or one press does two things.

/** The dialog on top, if any: each one is portalled to the end of <body> as it opens. */
export function topDialog(doc: Document = document): Element | null {
  const open = doc.querySelectorAll('[role="dialog"], [role="alertdialog"]');
  return open[open.length - 1] ?? null;
}

/** Whether `el` is in the dialog on top, or nothing is over the page at all. */
export function onTop(el: Element | null): boolean {
  if (!el) return false;
  const top = topDialog(el.ownerDocument);
  return top === null || top.contains(el);
}
