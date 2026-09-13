// A labelled action that becomes a compact glyph on narrow screens. Layout is
// entirely CSS-driven; the label remains in the DOM as the accessible name.

import { el as browserEl } from "./dom.js";

export function compactAction({
  label,
  glyph,
  className = "btn ghost",
  title = label,
  ...attributes
}, ui = browserEl) {
  return ui("button", {
    class: `${className} compact-action`,
    type: "button",
    title,
    ...attributes,
  }, [
    ui("span", { class: "compact-action-glyph", text: glyph, "aria-hidden": "true" }),
    ui("span", { class: "compact-action-label", text: label }),
  ]);
}
