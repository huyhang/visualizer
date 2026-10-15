import { undo } from "../history";
import { emptyDraft } from "./draft";
import {
  addScene,
  applyEdit,
  keep,
  moveScene,
  orderOf,
  removeScene,
  startComparing,
  startEditing,
  type Editing,
  type Side,
} from "./editing";

const base: Editing = {
  draft: { ...emptyDraft(), events: ["a", "b", "c"] },
  alternative: ["c", "b", "a"],
};
const titled = (title: string): Editing => ({ ...base, draft: { ...base.draft, title } });

describe("applyEdit", () => {
  it("folds a run of typing in one field into one step", () => {
    let state = startEditing(base.draft);
    state = applyEdit(state, titled("T"), "title");
    state = applyEdit(state, titled("Th"), "title");
    state = applyEdit(state, titled("The"), "title");
    expect(state.history.past).toHaveLength(1);
    expect(undo(state.history).present.draft.title).toBe("");
  });

  it("starts a new step when the field changes or something else is edited", () => {
    let state = startEditing(base.draft);
    state = applyEdit(state, titled("T"), "title");
    state = applyEdit(
      state,
      { ...titled("T"), draft: { ...titled("T").draft, overview: "o" } },
      "overview",
    );
    state = applyEdit(state, moveScene(state.history.present, "A", 0, 2));
    expect(state.history.past).toHaveLength(3);
    expect(state.typing).toBeNull();
  });

  it("forgets what was undone once typing continues", () => {
    let state = startEditing(base.draft);
    state = applyEdit(state, titled("A"), "title");
    state = { history: undo(state.history), typing: "title" };
    state = applyEdit(state, titled("B"), "title");
    expect(state.history.future).toEqual([]);
  });

  it("records nothing when nothing changed", () => {
    const state = startEditing(base.draft);
    expect(applyEdit(state, state.history.present).history).toBe(state.history);
  });
});

describe("orders", () => {
  it.each<[Side, (e: Editing, side: Side) => Editing, string[]]>([
    ["A", (e, s) => moveScene(e, s, 0, 2), ["b", "c", "a"]],
    ["B", (e, s) => moveScene(e, s, 0, 2), ["b", "a", "c"]],
    ["A", (e, s) => removeScene(e, s, 1), ["a", "c"]],
    ["B", (e, s) => removeScene(e, s, 0), ["b", "a"]],
    ["A", (e, s) => addScene(e, s, "x", 1), ["a", "x", "b", "c"]],
    ["B", (e, s) => addScene(e, s, "x"), ["c", "b", "a", "x"]],
  ])("edits order %s and leaves the other alone", (side, act, expected) => {
    const next = act(base, side);
    expect(orderOf(next, side)).toEqual(expected);
    const other: Side = side === "A" ? "B" : "A";
    expect(orderOf(next, other)).toEqual(orderOf(base, other));
  });

  it("starts a comparison from a copy of the current order", () => {
    const next = startComparing({ ...base, alternative: null });
    expect(next.alternative).toEqual(["a", "b", "c"]);
    expect(next.alternative).not.toBe(next.draft.events);
  });

  it.each<[Side, string[]]>([
    ["A", ["a", "b", "c"]],
    ["B", ["c", "b", "a"]],
  ])("keeping %s makes it the draft and ends the comparison", (side, events) => {
    expect(keep(base, side)).toEqual({
      draft: { ...base.draft, events },
      alternative: null,
    });
  });
});
