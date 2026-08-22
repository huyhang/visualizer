// The header's "A" control: the same four text sizes Articles and Timeline
// offer, stored per service so each remembers its own. The template applies a
// saved size before first paint; this handles the button and its label.

const KEY = "prithvi-fontscale";
const LEVELS = [
  { px: 16, name: "Normal" },
  { px: 18, name: "Large" },
  { px: 20, name: "Larger" },
  { px: 22, name: "Largest" },
];

function saved() {
  let stored = null;
  try {
    stored = localStorage.getItem(KEY);
  } catch (error) {
    // Private mode denies storage; the default size is a fine answer.
    return LEVELS[0];
  }
  return LEVELS.find((level) => level.px === parseInt(stored, 10)) || LEVELS[0];
}

export function initFontScale(button, onChange) {
  function apply(level) {
    document.documentElement.style.fontSize = `${level.px}px`;
    try {
      localStorage.setItem(KEY, String(level.px));
    } catch (error) {
      // As above: the size still applies for this page, it just will not stick.
    }
    button.title = `Text size: ${level.name}`;
    button.setAttribute("aria-label", button.title);
  }

  apply(saved());
  button.addEventListener("click", () => {
    apply(LEVELS[(LEVELS.indexOf(saved()) + 1) % LEVELS.length]);
    // Every rem-based dimension just changed, including the map stage; whoever
    // owns the drawing needs to re-fit it to the new viewport.
    if (onChange) onChange();
  });
}
