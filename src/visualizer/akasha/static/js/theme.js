// Light/dark theme toggle, persisted in localStorage. The initial value is set
// by an inline script in the template (before paint); this only handles toggles.

const KEY = "akasha-theme";

export function initTheme(button) {
  button.addEventListener("click", () => {
    const next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try { localStorage.setItem(KEY, next); } catch (e) { /* private mode */ }
  });
}
