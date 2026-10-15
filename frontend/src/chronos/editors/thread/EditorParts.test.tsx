import { footNote } from "./EditorParts";

describe("footNote", () => {
  it.each<[boolean, string[], boolean, string]>([
    [true, ["Name it."], false, "Keep A or B to save."],
    [false, ["Name it.", "Add a scene."], true, "Name it."],
    [false, [], true, "Nothing is written until you create it."],
    [false, [], false, "Findings never block a save."],
  ])(
    "comparing %s, problems %j, creating %s",
    (comparing, problems, creating, expected) => {
      expect(footNote(comparing, problems, creating)).toBe(expected);
    },
  );
});
