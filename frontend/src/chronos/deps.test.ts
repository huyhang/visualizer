import { windowLocation } from "./deps";

describe("windowLocation", () => {
  it.each(["push", "replace"] as const)(
    "tells the router about a %s at once, not when the browser gets round to it",
    (how) => {
      const location = windowLocation(window);
      const seen: string[] = [];
      const stop = location.subscribe(() => seen.push(location.current()));
      location[how](`#/after-${how}`);
      expect(seen).toContain(`#/after-${how}`);
      stop();
    },
  );
});
