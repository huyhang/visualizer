import { plainBody, plural, slugify, timeframe, type Timed } from "./text";

describe("timeframe", () => {
  it.each<[string, Timed, string]>([
    ["a span", { start_label: "Day 3", end_label: "Day 4" }, "Day 3 → Day 4"],
    ["an instant", { start_label: "Day 3", end_label: "Day 3" }, "Day 3"],
    ["no end", { start_label: "Day 3" }, "Day 3"],
    ["plain ticks", { start_tick: 24, end_tick: 48 }, "24"],
    ["tick zero", { start_tick: 0 }, "0"],
    ["unscheduled", { scheduled: false, start_label: "Day 3" }, "unscheduled"],
    ["nothing known", {}, "unscheduled"],
  ])("reads %s", (_, scene, expected) => {
    expect(timeframe(scene)).toBe(expected);
  });
});

describe("plainBody", () => {
  it.each<[string | null, string]>([
    ["Sworn to [[locations/highkeep|Highkeep]].", "Sworn to Highkeep."],
    ["Rides with [[characters/lyra]].", "Rides with lyra."],
    ["No links at all.", "No links at all."],
    [null, ""],
  ])("unwraps %j", (body, expected) => {
    expect(plainBody(body)).toBe(expected);
  });
});

describe("plural", () => {
  it.each<[number, string]>([
    [0, "0 problems"],
    [1, "1 problem"],
    [2, "2 problems"],
  ])("counts %i", (count, expected) => {
    expect(plural(count, "problem")).toBe(expected);
  });
});

describe("slugify", () => {
  it.each<[string, string]>([
    ["The Knight's Road", "the-knights-road"],
    ["The Knight’s Road", "the-knights-road"],
    ["  Harbor -- Exchange!  ", "harbor-exchange"],
    ["~scenes", "scenes"],
    ["???", ""],
  ])("turns %j into %j", (title, expected) => {
    expect(slugify(title)).toBe(expected);
  });
});
