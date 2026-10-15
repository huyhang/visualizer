import { followTitle, idProblem } from "./ids";

describe("followTitle", () => {
  it.each<[string, string, boolean, string]>([
    ["The Harbor Exchange", "", false, "the-harbor-exchange"],
    ["The Harbor Exchange", "harbor", true, "harbor"],
    ["", "anything", false, ""],
  ])("title %j, id %j, taken over %s", (title, id, takenOver, expected) => {
    expect(followTitle(title, id, takenOver)).toBe(expected);
  });
});

describe("idProblem", () => {
  it.each<[string, string[], string | null]>([
    ["harbor-exchange", [], null],
    ["", [], "Give it a name or an id."],
    ["Harbor Exchange", [], "Use lowercase letters, digits and hyphens."],
    ["-harbor", [], "Use lowercase letters, digits and hyphens."],
    ["road", ["road", "tale"], "That id is already taken in this book."],
  ])("%j among %j", (id, taken, expected) => {
    expect(idProblem(id, taken)).toBe(expected);
  });
});
