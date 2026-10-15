import { vi } from "vitest";
import { doc, para, text } from "../test/docs";
import { AT, CHAPTER, fakeApi, fakeState, type FakeState } from "../test/fakeApi";
import { handTimer } from "../test/renderWriter";
import { createDraftSession } from "./draftSession";
import { memoryRecovery, recoveryKey, type RecoverySnapshot } from "./recovery";

function session(
  patch: Partial<FakeState> = {},
  recovered: RecoverySnapshot | null = null,
) {
  const { api, state } = fakeApi(fakeState(patch));
  const clock = handTimer();
  const recovery = memoryRecovery();
  const navigate = vi.fn();
  let words = CHAPTER;
  const reader = { document: () => words, caret: () => ({ block: "p2", offset: 3 }) };
  const store = createDraftSession(
    {
      manuscript: state.manuscript,
      at: AT,
      section: state.section,
      listing: { drafts: state.drafts, section_rev: state.sectionRev },
      draft: state.drafts[0]!,
      recovered,
    },
    {
      api,
      recovery,
      timer: clock.timer,
      navigate,
      user: "mara",
      reader,
      now: () => new Date("2026-10-14T12:00:00Z"),
    },
  );
  const type = (value: string) => {
    words = doc(para("p1", text(value)));
    store.changed();
  };
  return { store, api, state, clock, recovery, navigate, type };
}

const key = recoveryKey({ user: "mara", ...AT, draft: "draft-1" });

describe("draft session", () => {
  it("keeps typing on this device at once, and on the server once typing pauses", async () => {
    const { store, api, clock, recovery, type } = session();
    type("New words.");
    expect(store.getState().status.state).toBe("local");
    expect((await recovery.get(key))?.document).toEqual(
      doc(para("p1", text("New words."))),
    );
    clock.runAll();
    await vi.waitFor(() => expect(store.getState().status.state).toBe("saved"));
    expect(api.saveDraft).toHaveBeenCalledWith(
      AT,
      "draft-1",
      { name: "Draft 1", document: doc(para("p1", text("New words."))) },
      3,
      false,
    );
    expect(store.getState().drafts.current.rev).toBe(4);
    expect(await recovery.get(key)).toBeNull();
  });

  it("saves a new title after the draft, guarded by the section's revision", async () => {
    const { store, api } = session();
    store.setTitle("  The Broken Gate ");
    await store.actions.settled();
    expect(api.updateSectionTitle).toHaveBeenCalledWith(AT, "The Broken Gate", 5);
    expect(store.getState().drafts.sectionRev).toBe(6);
  });

  it.each<[number, string]>([
    [409, "conflict"],
    [422, "invalid"],
    [503, "offline"],
  ])(
    "a save answered %i leaves the words %s, still on this device",
    async (status, state) => {
      const { store, recovery, type } = session({ failSaves: status });
      type("Mine.");
      expect(await store.actions.settled()).toBe(false);
      expect(store.getState().status.state).toBe(state);
      expect(await recovery.get(key)).not.toBeNull();
    },
  );

  it("does not leave while words are unsaved", async () => {
    const { store, navigate, type } = session({ failSaves: 503 });
    type("Mine.");
    await store.actions.leave("/elsewhere");
    await store.actions.newDraft("Another");
    expect(navigate).not.toHaveBeenCalled();
  });

  it("preserves a conflict as a new draft holding the writer's words", async () => {
    const { store, api, state, navigate, recovery, type } = session({ failSaves: 409 });
    type("Mine, not theirs.");
    await store.actions.settled();
    state.failSaves = null;
    await store.actions.preserveConflict();
    expect(api.createDraft).toHaveBeenCalledWith(
      AT,
      expect.stringMatching(/^Recovered /),
      "draft-1",
    );
    expect(state.drafts[1]?.document).toEqual(doc(para("p1", text("Mine, not theirs."))));
    expect(navigate).toHaveBeenCalledWith("/write/one/gate?draft=draft-2");
    expect(await recovery.get(key)).toBeNull();
  });

  it("renames the draft, saving the new name", async () => {
    const { store, api } = session();
    store.actions.rename("Alternate");
    await store.actions.settled();
    expect(api.saveDraft).toHaveBeenCalledWith(
      AT,
      "draft-1",
      expect.objectContaining({ name: "Alternate" }),
      3,
      false,
    );
    expect(store.getState().drafts.rows[0]?.name).toBe("Alternate");
  });

  it("makes the open draft primary with the section's revision", async () => {
    const extra = {
      id: "draft-2",
      name: "Draft 2",
      primary: false,
      rev: 1,
      document: CHAPTER,
    };
    const { api, state } = fakeApi(fakeState());
    state.drafts.push(extra);
    const store = createDraftSession(
      {
        manuscript: state.manuscript,
        at: AT,
        section: state.section,
        listing: { drafts: state.drafts, section_rev: 5 },
        draft: extra,
        recovered: null,
      },
      {
        api,
        recovery: memoryRecovery(),
        timer: handTimer().timer,
        navigate: vi.fn(),
        user: "mara",
        reader: { document: () => CHAPTER, caret: () => null },
      },
    );
    await store.actions.makePrimary();
    expect(api.makePrimary).toHaveBeenCalledWith(AT, "draft-2", 5);
    expect(store.getState().drafts.rows.map((row) => row.primary)).toEqual([false, true]);
  });

  it("creates a chapter under a free id and opens it", async () => {
    const { store, api, navigate } = session();
    await store.actions.createChapter("one", "Gate");
    expect(api.createSection).toHaveBeenCalledWith("ember", "one", "gate-2", {
      kind: "chapter",
      title: "Gate",
    });
    expect(navigate).toHaveBeenCalledWith("/write/one/gate-2");
  });

  it("returns to the reader at the paragraph the caret is in", async () => {
    const { store, navigate } = session();
    await store.actions.done();
    expect(navigate).toHaveBeenCalledWith("/read/one/gate#p2?draft=draft-1");
  });

  it.each<[number, string]>([
    [3, "local"],
    [2, "conflict"],
  ])("resumes words kept over revision %i as %s", (draftRev, state) => {
    const kept: RecoverySnapshot = {
      document: CHAPTER,
      name: "Draft 1",
      title: "",
      draftRev,
      caret: null,
      savedAt: "",
    };
    const { store } = session({}, kept);
    store.resume();
    expect(store.getState().status.state).toBe(state);
  });

  it("tells its subscribers when anything changes", () => {
    const { store } = session();
    const heard = vi.fn();
    const stop = store.subscribe(heard);
    store.setTitle("x");
    stop();
    store.setTitle("y");
    expect(heard).toHaveBeenCalledTimes(2); // the title, then "saved on this device"
  });
});
