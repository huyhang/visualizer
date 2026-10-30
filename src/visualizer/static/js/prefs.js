// Text size and theme (light, paper, dark), for all three services.
//
// One pair of keys, not one pair per service. The three apps are one product
// behind one origin, and someone who makes the text bigger in Articles means it
// bigger everywhere. They used to keep `akasha-*`, `chronos-*` and `prithvi-*`
// separately, with seven copies of this logic between them, so the setting
// silently reset every time you changed tab.
//
// A *classic* script, loaded blocking in <head>, because it has to run before
// first paint -- a module is deferred, which shows a flash of the wrong theme
// and the wrong size. Everything past the first two calls waits for the DOM.

(function () {
  var THEME = "visualizer-theme";
  var SIZE = "visualizer-fontscale";
  // Read once, so a preference set before the keys were shared still applies.
  // `kb-*` predates the rename to Akasha and is still honoured.
  var OLD_THEME = ["akasha-theme", "chronos-theme", "prithvi-theme", "kb-theme"];
  var OLD_SIZE = [
    "akasha-fontscale", "chronos-fontscale", "prithvi-fontscale", "kb-fontscale",
  ];

  var LEVELS = [
    { px: 16, name: "Normal" },
    { px: 18, name: "Large" },
    { px: 20, name: "Larger" },
    { px: 22, name: "Largest" },
  ];

  function read(key, fallbacks) {
    try {
      var value = localStorage.getItem(key);
      if (value !== null) return value;
      for (var i = 0; i < fallbacks.length; i++) {
        value = localStorage.getItem(fallbacks[i]);
        if (value !== null) return value;
      }
    } catch (e) {
      // Private mode denies storage; the default is a fine answer.
    }
    return null;
  }

  function write(key, value) {
    try {
      localStorage.setItem(key, value);
    } catch (e) {
      // As above: it applies to this page, it just will not be remembered.
    }
  }

  function prefersDark() {
    try {
      return window.matchMedia("(prefers-color-scheme: dark)").matches;
    } catch (e) {
      return false;
    }
  }

  function theme() {
    // A name this page does not know -- written by a newer one, or by hand --
    // is treated as never chosen, not painted as a theme with no colours.
    var saved = known(read(THEME, OLD_THEME));
    return saved ? saved.id : prefersDark() ? "dark" : "light";
  }

  function level() {
    var px = parseInt(read(SIZE, OLD_SIZE), 10);
    for (var i = 0; i < LEVELS.length; i++) {
      if (LEVELS[i].px === px) return LEVELS[i];
    }
    return LEVELS[0];
  }

  // The order the theme button steps through. Paper sits between the two it
  // is closest to: one press from light, one from dark.
  var THEMES = [
    { id: "light", name: "Light" },
    { id: "paper", name: "Paper" },
    { id: "dark", name: "Dark" },
  ];

  function known(id) {
    for (var i = 0; i < THEMES.length; i++) {
      if (THEMES[i].id === id) return THEMES[i];
    }
    return null;
  }

  function applyTheme(name) {
    document.documentElement.setAttribute("data-theme", name);
  }

  function applySize(chosen) {
    document.documentElement.style.fontSize = chosen.px + "px";
  }

  // -- before paint -----------------------------------------------------------
  applyTheme(theme());
  applySize(level());

  // -- the controls, on whichever pages have them -----------------------------

  function describe(button, chosen) {
    button.title = "Text size: " + chosen.name;
    button.setAttribute("aria-label", button.title);
  }

  // Says what the theme is now, so a button that cycles three ways is not a
  // guess -- the same courtesy the size button pays.
  function describeTheme(button, id) {
    button.title = "Theme: " + known(id).name;
    button.setAttribute("aria-label", button.title);
  }

  function wire() {
    var themeButton = document.getElementById("theme-toggle");
    if (themeButton) {
      describeTheme(themeButton, theme());
      themeButton.addEventListener("click", function () {
        var now = known(document.documentElement.getAttribute("data-theme"));
        var next = THEMES[(THEMES.indexOf(now) + 1) % THEMES.length].id;
        applyTheme(next);
        write(THEME, next);
        describeTheme(themeButton, next);
      });
    }

    var sizeButton = document.getElementById("font-toggle");
    if (sizeButton) {
      describe(sizeButton, level());
      sizeButton.addEventListener("click", function () {
        var next = LEVELS[(LEVELS.indexOf(level()) + 1) % LEVELS.length];
        applySize(next);
        write(SIZE, String(next.px));
        describe(sizeButton, next);
        // Every rem-based dimension just changed. Prithvi re-fits its map on
        // this; nothing else needs to care that it happened.
        document.dispatchEvent(
          new CustomEvent("prefs:fontscale", { detail: next })
        );
      });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", wire);
  } else {
    wire();
  }
})();
