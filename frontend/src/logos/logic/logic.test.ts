import { vi } from "vitest";
import { LogosApiError, saveFailure } from "../api/errors";
import type { Draft, Manuscript, ReviewIssue, Turn } from "../api/types";
import { doc, para, text } from "../test/docs";
import { createAutosave, type Timer } from "./autosave";
import { compareDocuments, draftStats } from "./comparison";
import {
  chooseDraft,
  draftCapabilities,
  draftOptions,
  promoted,
  renamed,
  saved,
  type DraftState,
} from "./drafts";
import { fixDiff } from "./fixDiff";
import { menuPosition } from "./menu";
import {
  allSectionIds,
  availableId,
  filterOutline,
  findSection,
  sectionLabel,
  sectionName,
} from "./outline";
import { memoryStore, storedPreferences } from "./preferences";
import { memoryRecovery, recoveryKey } from "./recovery";
import {
  availabilityTone,
  coachAnnotations,
  currentFix,
  editorAnnotations,
  issueCounts,
  listedIssues,
  pollDelay,
  stageLabel,
  stanceOf,
  stepIssue,
  verificationLabel,
} from "./review";

// -- autosave ---------------------------------------------------------------------

function manualTimer() {
  let queued: (() => void) | null = null;
  const timer: Timer = {
    set: (run) => {
      queued = run;
      return 1;
    },
    clear: () => {
      queued = null;
    },
  };
  return { timer, fire: () => queued?.() };
}

describe("autosave", () => {
  it("keeps the newest snapshot when a save fails while the writer kept typing", async () => {
    const { timer } = manualTimer();
    const states: string[] = [];
    const remote: string[] = [];
    let release: (value?: unknown) => void = () => {};
    const autosave = createAutosave<string>({
      timer,
      saveLocal: vi.fn(),
      saveRemote: (snapshot) => {
        remote.push(snapshot);
        return new Promise((_, reject) => {
          release = () => reject(new LogosApiError(503, "down"));
        });
      },
      onState: (state) => states.push(state),
      classify: saveFailure,
    });
    autosave.schedule("first");
    const flushing = autosave.flush();
    autosave.schedule("second");
    release();
    await flushing;
    expect(remote).toEqual(["first"]);
    expect(states.at(-1)).toBe("offline");
    expect(autosave.hasPending()).toBe(true);
  });

  it.each<[number, string]>([
    [409, "conflict"],
    [422, "invalid"],
    [500, "offline"],
  ])("a %i is a %s", async (status, state) => {
    const { timer } = manualTimer();
    const onState = vi.fn();
    const autosave = createAutosave<string>({
      timer,
      saveLocal: vi.fn(),
      saveRemote: () => Promise.reject(new LogosApiError(status, "no")),
      onState,
      classify: saveFailure,
    });
    autosave.schedule("words");
    await autosave.flush();
    expect(onState).toHaveBeenLastCalledWith(state, expect.any(LogosApiError));
  });

  it("clears the device copy once the server has the words", async () => {
    const { timer, fire } = manualTimer();
    const saveLocal = vi.fn();
    const autosave = createAutosave<string>({
      timer,
      saveLocal,
      saveRemote: () => Promise.resolve(),
      onState: vi.fn(),
      classify: saveFailure,
    });
    autosave.schedule("words");
    fire();
    await autosave.flush();
    expect(saveLocal.mock.calls).toEqual([["words"], [null]]);
    expect(autosave.hasPending()).toBe(false);
  });
});

// -- recovery and preferences ---------------------------------------------------------

describe("recovery", () => {
  it("scopes copies to the account and the draft", () => {
    const place = { user: "mara", book: "b", volume: "v", section: "s", draft: "d/1" };
    expect(recoveryKey(place)).toBe("mara/b/v/s/d%2F1");
    expect(recoveryKey({ ...place, user: "ivo" })).not.toBe(recoveryKey(place));
  });

  it("keeps and forgets a snapshot", async () => {
    const store = memoryRecovery();
    const snapshot = {
      document: doc(),
      name: "Draft",
      title: "",
      draftRev: 1,
      caret: null,
      savedAt: "now",
    };
    await store.set("k", snapshot);
    expect(await store.get("k")).toEqual(snapshot);
    await store.remove("k");
    expect(await store.get("k")).toBeNull();
  });
});

describe("preferences", () => {
  it("shares the dialect and ignored rules with the reader's keys", () => {
    const store = memoryStore({ "logos-writing-dialect:mara": "en-GB" });
    const prefs = storedPreferences(store, "mara");
    expect(prefs.dialect()).toBe("en-GB");
    prefs.ignoreRule("Adverb");
    prefs.ignoreRule("Adverb");
    expect(store.getItem("logos-writing-ignored:mara")).toBe('["Adverb"]');
  });

  it.each<[string | undefined, object]>([
    [undefined, { checks: ["continuity", "anachronism", "prose"], verify: "auto" }],
    ['{"checks":["prose"],"verify":"off"}', { checks: ["prose"], verify: "off" }],
    [
      '{"checks":[],"verify":"off"}',
      { checks: ["continuity", "anachronism", "prose"], verify: "auto" },
    ],
    ["not json", { checks: ["continuity", "anachronism", "prose"], verify: "auto" }],
  ])("review options from %j", (raw, expected) => {
    const store = memoryStore(
      raw === undefined ? {} : { "logos-review-options:mara": raw },
    );
    expect(storedPreferences(store, "mara").reviewOptions()).toEqual(expected);
  });
});

// -- drafts ---------------------------------------------------------------------------

const draft = (id: string, primary = false): Draft => ({
  id,
  name: id,
  primary,
  rev: 1,
  document: doc(),
});
const state = (): DraftState => ({
  rows: [
    { id: "a", name: "a", primary: true, rev: 1 },
    { id: "b", name: "b", primary: false, rev: 1 },
  ],
  current: draft("b"),
  sectionRev: 3,
});

describe("drafts", () => {
  it("renames the open draft and its row together", () => {
    const next = renamed(state(), "Alternate");
    expect(next.current.name).toBe("Alternate");
    expect(draftOptions(next).map((o) => o.label)).toEqual(["a (Primary)", "Alternate"]);
  });

  it("moves the primary flag off every other draft", () => {
    const next = promoted(state(), 4);
    expect(next.rows.map((row) => row.primary)).toEqual([false, true]);
    expect(next.sectionRev).toBe(4);
  });

  it("adopts a save and carries it into the row", () => {
    const next = saved(state(), { ...draft("b"), rev: 7, word_count: 12, section_rev: 5 });
    expect(next.current.rev).toBe(7);
    expect(next.rows[1]).toMatchObject({ rev: 7, word_count: 12 });
    expect(next.sectionRev).toBe(5);
  });

  it.each<[number, boolean, object]>([
    [
      1,
      true,
      { canSwitch: false, canCompare: false, canPromote: false, showPrimaryBadge: false },
    ],
    [
      2,
      true,
      { canSwitch: true, canCompare: true, canPromote: false, showPrimaryBadge: true },
    ],
    [
      2,
      false,
      { canSwitch: true, canCompare: true, canPromote: true, showPrimaryBadge: false },
    ],
  ])("with %i drafts, primary=%s: %j", (count, primary, expected) => {
    expect(draftCapabilities(count, primary)).toEqual(expected);
  });

  it.each<[string | null, string]>([
    ["b", "b"],
    ["gone", "a"],
    [null, "a"],
  ])("asked for %j, opens %j", (requested, expected) => {
    expect(chooseDraft(state().rows, requested)?.id).toBe(expected);
  });
});

// -- comparison ---------------------------------------------------------------------

describe("comparison", () => {
  it("aligns blocks by id and reports what changed", () => {
    const left = doc(
      para("a", text("Same.")),
      para("b", text("Old.")),
      para("c", text("Gone.")),
    );
    const right = doc(
      para("a", text("Same.")),
      para("b", text("New.")),
      para("d", text("Added.")),
    );
    expect(compareDocuments(left, right).rows.map((r) => [r.id, r.status])).toEqual([
      ["a", "same"],
      ["b", "changed"],
      ["d", "added"],
      ["c", "removed"],
    ]);
  });

  it("counts words, paragraphs and sentence length", () => {
    expect(
      draftStats(doc(para("a", text("One two. Three four five.")), para("b"))),
    ).toEqual({
      words: 5,
      paragraphs: 2,
      sentences: 2,
      averageSentenceWords: 3,
    });
  });
});

// -- outline ------------------------------------------------------------------------

const manuscript = (): Manuscript => ({
  book: "ember",
  title: "Ember",
  world: "ember",
  rev: 1,
  permissions: { read: true, write: true },
  volumes: [
    {
      id: "one",
      number: 1,
      title: "Volume One",
      sections: [
        {
          id: "prologue",
          volume: "one",
          kind: "prologue",
          number: null,
          title: null,
          primary_draft_id: "d",
          rev: 1,
        },
        {
          id: "gate",
          volume: "one",
          kind: "chapter",
          number: 1,
          title: "The Gate",
          primary_draft_id: "d",
          rev: 1,
        },
      ],
    },
    {
      id: "two",
      number: 2,
      title: "Volume Two",
      sections: [
        {
          id: "tea",
          volume: "two",
          kind: "chapter",
          number: 2,
          title: "Tea",
          primary_draft_id: "d",
          rev: 1,
        },
      ],
    },
  ],
  section_aliases: [{ source_volume: "old", section: "tea", target_volume: "two" }],
});

describe("outline", () => {
  it("names untitled sections by their kind", () => {
    const [prologue, gate] = manuscript().volumes[0]!.sections;
    expect([sectionName(prologue!), sectionLabel(gate!), sectionName(gate!)]).toEqual([
      "Prologue",
      "Chapter 1",
      "The Gate",
    ]);
  });

  it.each<[string, string[]]>([
    ["", ["prologue", "gate", "tea"]],
    ["gate", ["gate"]],
    ["volume 2", ["tea"]],
    ["chapter", ["gate", "tea"]],
    ["nothing", []],
  ])("filtering by %j shows %j", (query, expected) => {
    expect(
      filterOutline(manuscript(), query).flatMap((v) => v.sections.map((s) => s.id)),
    ).toEqual(expected);
  });

  it.each<[string, string]>([
    ["The Gate", "the-gate-2"],
    ["Tea", "tea-2"],
    ["Île de la Cité", "ile-de-la-cite"],
    ["!!!", "chapter"],
  ])("a section titled %j gets the id %j", (title, expected) => {
    const known = new Set([...allSectionIds(manuscript()), "the-gate"]);
    expect(availableId(title, known, "chapter")).toBe(expected);
  });

  it("follows a moved section's alias, and fails shut on an unknown one", () => {
    expect(findSection(manuscript(), "old", "tea")?.volume.id).toBe("two");
    expect(findSection(manuscript(), "one", "nowhere")).toBeNull();
  });
});

// -- review ---------------------------------------------------------------------------

const turn = (
  role: Turn["role"],
  stance: Turn["stance"] = null,
  fix: Partial<Turn> = {},
): Turn => ({
  role,
  text: "…",
  at: null,
  stance,
  suggestion: null,
  replacement: null,
  model: null,
  ...fix,
});

const issue = (id: string, patch: Partial<ReviewIssue> = {}): ReviewIssue => ({
  id,
  check: "prose",
  severity: "info",
  confidence: "possible",
  block: "a",
  quote: "words",
  message: "A note.",
  suggestion: "Advice.",
  replacement: "better words",
  reference: null,
  verified: null,
  status: "open",
  dismissed_before: null,
  discussion: [],
  reply: null,
  stale: false,
  ...patch,
});

describe("review", () => {
  it("draws only open issues", () => {
    const drawn = editorAnnotations([
      issue("1"),
      issue("2", { status: "dismissed" }),
      issue("3", { status: "resolved" }),
    ]);
    expect(drawn.map((a) => a.id)).toEqual(["editor:1"]);
  });

  it("draws coach findings by their excerpt", () => {
    expect(
      coachAnnotations([
        {
          id: "x",
          block: "b",
          category: "flow",
          title: "Adverb",
          message: "",
          excerpt: "very",
          replacement: null,
        },
      ]),
    ).toEqual([
      {
        id: "coach:x",
        source: "coach",
        kind: "flow",
        severity: "info",
        blockId: "b",
        quote: "very",
      },
    ]);
  });

  it.each<[string, Turn[], object, string | null]>([
    [
      "no discussion",
      [],
      { suggestion: "Advice.", replacement: "better words", revised: false },
      null,
    ],
    [
      "a revision",
      [
        turn("writer"),
        turn("editor", "revises", { suggestion: "Try this.", replacement: "other words" }),
      ],
      { suggestion: "Try this.", replacement: "other words", revised: true },
      "revises",
    ],
    [
      "a later maintain keeps the revision",
      [
        turn("editor", "revises", { suggestion: "Try this.", replacement: null }),
        turn("writer"),
        turn("editor", "maintains"),
      ],
      { suggestion: "Try this.", replacement: null, revised: true },
      "maintains",
    ],
    [
      "a withdrawal",
      [turn("writer"), turn("editor", "withdraws")],
      { suggestion: "Advice.", replacement: "better words", revised: false },
      "withdraws",
    ],
  ])("after %s", (_name, discussion, fix, stance) => {
    const subject = issue("1", { discussion });
    expect(currentFix(subject)).toEqual(fix);
    expect(stanceOf(subject)).toBe(stance);
  });

  it.each<[boolean, boolean, number | false]>([
    [true, true, 3000],
    [true, false, 30_000],
    [false, true, false],
  ])("active=%s visible=%s polls every %s", (active, visible, expected) => {
    expect(pollDelay(active, visible)).toBe(expected);
  });

  it("lists issues in reading order, filtered", () => {
    const issues = [
      issue("late", { block: "b" }),
      issue("second", { block: "a" }),
      issue("first", { block: "a" }),
      issue("done", { block: "a", status: "resolved" }),
      issue("canon", { block: "a", check: "continuity" }),
    ];
    const placement = {
      "editor:first": { from: 2, to: 4 },
      "editor:second": { from: 8, to: 9 },
    };
    const ids = (filter: "open" | "done" | "all", checks = ["prose" as const]) =>
      listedIssues(issues, filter, checks, ["a", "b"], placement).map((i) => i.id);
    expect(ids("open")).toEqual(["first", "second", "late"]);
    expect(ids("done")).toEqual(["done"]);
    expect(ids("all", ["prose"])).toHaveLength(4);
    expect(issueCounts(issues)).toEqual({ open: 4, dismissed: 0, resolved: 1, total: 5 });
  });

  it.each<[string | null, 1 | -1, string]>([
    [null, 1, "a"],
    [null, -1, "c"],
    ["a", 1, "b"],
    ["c", 1, "a"],
    ["a", -1, "c"],
  ])("from %j, a step of %i lands on %j", (current, step, expected) => {
    expect(stepIssue([issue("a"), issue("b"), issue("c")], current, step)?.id).toBe(
      expected,
    );
  });

  it.each<[Parameters<typeof availabilityTone>[0], string]>([
    ["ready", "ok"],
    ["cold", "warn"],
    ["busy", "warn"],
    ["misconfigured", "danger"],
    ["unreachable", "off"],
    ["off", "off"],
  ])("%s is shown as %s", (state, tone) => expect(availabilityTone(state)).toBe(tone));

  it.each<[Parameters<typeof stageLabel>[0], Parameters<typeof stageLabel>[1], string]>([
    ["queued", null, "Waiting its turn"],
    ["running", { stage: "loading_model" }, "Waking the editor"],
    ["running", { stage: "second_check" }, "Second-checking each issue"],
    ["running", { stage: "mystery", message: "Doing a thing" }, "Doing a thing"],
  ])("%s at %j reads %j", (state, progress, label) =>
    expect(stageLabel(state, progress)).toBe(label),
  );

  it.each<[object | null, string]>([
    [{ status: "checked", model: "m", checked: 3, removed: 0 }, "Second-checked"],
    [
      { status: "checked", model: "m", checked: 3, removed: 2 },
      "Second-checked · 2 doubtful issues removed",
    ],
    [
      { status: "skipped", model: null, checked: 0, removed: 0 },
      "First pass only · the second checker was away",
    ],
    [{ status: "off", model: null, checked: 0, removed: 0 }, "First pass only"],
    [null, ""],
  ])("verification %j reads %j", (verification, expected) => {
    expect(verificationLabel({ verification } as never)).toBe(expected);
  });
});

describe("menuPosition", () => {
  it.each<[{ x: number; y: number }, { left: number; top: number }]>([
    [
      { x: 10, y: 10 },
      { left: 10, top: 10 },
    ],
    [
      { x: 390, y: 790 },
      { left: 192, top: 692 },
    ],
    [
      { x: -5, y: -5 },
      { left: 8, top: 8 },
    ],
  ])("a menu opened at %j sits at %j", (pointer, expected) => {
    expect(
      menuPosition(pointer, { width: 200, height: 100 }, { width: 400, height: 800 }),
    ).toEqual(expected);
  });
});

describe("fixDiff", () => {
  it.each<[string, string, object]>([
    [
      "lifted the teapot and poured",
      "lifted the kettle and poured",
      { before: "lifted the ", removed: "teapot ", added: "kettle ", after: "and poured" },
    ],
    [
      "the teapot",
      "the old teapot",
      { before: "the ", removed: "", added: "old ", after: "teapot" },
    ],
    [
      "Winter came early",
      "[Fake fix] Winter came early",
      { before: "", removed: "", added: "[Fake fix] ", after: "Winter came early" },
    ],
    [
      "very quickly ran",
      "ran",
      { before: "", removed: "very quickly ", added: "", after: "ran" },
    ],
    [
      "grey eyes",
      "brown eyes",
      { before: "", removed: "grey ", added: "brown ", after: "eyes" },
    ],
  ])("%j -> %j", (quote, replacement, expected) => {
    expect(fixDiff(quote, replacement)).toEqual(expected);
  });
});
