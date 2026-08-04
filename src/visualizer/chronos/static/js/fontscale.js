// Text-size control: scales the whole UI by setting the root font size, which
// every rem-based dimension follows. Cycles through a few levels and persists
// the choice. The no-flash init in the template applies a saved value before
// paint; this only handles the button and labelling.

const KEY = "chronos-fontscale";
const LEVELS = [
  { px: 16, name: "Normal" },
  { px: 18, name: "Large" },
  { px: 20, name: "Larger" },
  { px: 22, name: "Largest" },
];

function saved() {
  const px = parseInt(localStorage.getItem(KEY) || "", 10);
  return LEVELS.find((l) => l.px === px) || LEVELS[0];
}

export function initFontScale(button) {
  function apply(level) {
    document.documentElement.style.fontSize = `${level.px}px`;
    try { localStorage.setItem(KEY, String(level.px)); } catch (e) { /* private mode */ }
    button.title = `Text size: ${level.name}`;
    button.setAttribute("aria-label", button.title);
  }

  apply(saved()); // sets the label; the size itself was already applied pre-paint

  button.addEventListener("click", () => {
    const idx = LEVELS.indexOf(saved());
    apply(LEVELS[(idx + 1) % LEVELS.length]);
  });
}
