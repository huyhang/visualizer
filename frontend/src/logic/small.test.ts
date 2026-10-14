// The small rules: progress and polling, the box's pill, the ask box, plans,
// formatting and link targets.

import { describe, expect, it } from "vitest";
import type { AvailabilityState, Job } from "../api/types";
import { job } from "../test/fixtures";
import { askRequest, DEFAULT_OPTIONS, parseLanguages, questionProblem } from "./ask";
import { boxLabel, boxTone, verifierLine } from "./availability";
import { plural, siteOf, slugOf, timeAgo } from "./format";
import { cleanQueries, planProblem } from "./plan";
import {
  BACKGROUND_MS,
  pollInterval,
  stageStates,
  waitingLine,
  WATCHING_MS,
} from "./progress";
import { resolveTarget } from "./refs";

describe("stageStates", () => {
  it.each<[Partial<Job>, string]>([
    [{ state: "queued" }, "todo todo todo todo todo todo todo"],
    [
      { state: "running", progress: { stage: "loading_model" } },
      "todo todo todo todo todo todo todo",
    ],
    [
      { state: "running", progress: { stage: "fetching" } },
      "done done current todo todo todo todo",
    ],
    [
      { state: "running", progress: { stage: "writing" } },
      "done done done done done done current",
    ],
    [{ state: "importing" }, "done done done done done done done"],
  ])("%j", (fields, expected) => {
    expect(stageStates(job(fields)).join(" ")).toBe(expected);
  });
});

describe("waitingLine", () => {
  it.each<[Partial<Job>, RegExp | null]>([
    [{ state: "submitting" }, /Sending/],
    [{ state: "queued" }, /Waiting/],
    [{ state: "running", progress: { stage: "loading_model" } }, /Loading the model/],
    [{ state: "importing" }, /Bringing/],
    [{ state: "running", progress: { stage: "searching", message: "Searching" } }, null],
  ])("%j", (fields, expected) => {
    const line = waitingLine(job(fields));
    if (expected) expect(line).toMatch(expected);
    else expect(line).toBeNull();
  });
});

describe("pollInterval", () => {
  it.each<[Job["state"] | undefined, boolean, number | false]>([
    ["running", true, WATCHING_MS],
    ["running", false, BACKGROUND_MS],
    ["queued", true, WATCHING_MS],
    ["submitting", true, WATCHING_MS],
    ["importing", true, WATCHING_MS],
    ["awaiting_approval", true, BACKGROUND_MS],
    ["done", true, false],
    ["failed", true, false],
    ["cancelled", true, false],
    [undefined, true, false],
  ])("%s, visible %s -> %s", (state, visible, expected) => {
    expect(pollInterval(state ? job({ state }) : undefined, visible)).toBe(expected);
  });
});

describe("the box's pill", () => {
  it.each<[AvailabilityState, string, string]>([
    ["ready", "Ready", "ok"],
    ["cold", "Warming up", "ok"],
    ["busy", "Busy", "warn"],
    ["queue_full", "Queue full", "warn"],
    ["degraded", "Degraded", "warn"],
    ["unreachable", "Asleep", "off"],
    ["misconfigured", "Misconfigured", "off"],
    ["incompatible", "Incompatible", "off"],
    ["off", "Off", "off"],
  ])("%s", (state, label, tone) => {
    expect([boxLabel(state), boxTone(state)]).toEqual([label, tone]);
  });

  it.each([
    ["up", /second-checked/],
    ["down", /down/],
    ["not_configured", /No second checker/],
  ] as const)("verifier %s", (verifier, expected) => {
    expect(
      verifierLine({
        state: "ready",
        can_submit: true,
        message: "",
        model: "m",
        verifier,
        private: true,
      }),
    ).toMatch(expected);
  });
});

describe("the ask box", () => {
  it.each([
    ["en", ["en"]],
    ["en, zh-TW  ja", ["en", "zh-TW", "ja"]],
    ["en,en", ["en"]],
    ["", "Name at least one language, such as en."],
    ["a b c d e f", "At most five languages."],
    ["EN", '"EN" is not a language code like en or zh-TW.'],
  ])("parseLanguages(%j)", (text, expected) => {
    expect(parseLanguages(text)).toEqual(expected);
  });

  it.each([
    ["ab", /three characters/],
    ["   abc   ", null],
    ["x".repeat(501), /under 500/],
  ])("questionProblem(%j)", (question, expected) => {
    const problem = questionProblem(question);
    if (expected) expect(problem).toMatch(expected);
    else expect(problem).toBeNull();
  });

  it.each([
    [
      DEFAULT_OPTIONS,
      null,
      {
        languages: ["en"],
        max_sources: 8,
        include_images: true,
        approve_plan: false,
        verify: "auto",
      },
    ],
    [
      { ...DEFAULT_OPTIONS, maxSources: 40, reviewPlan: true },
      "rj_0123456789abcdef",
      { max_sources: 15, approve_plan: true, parent: "rj_0123456789abcdef" },
    ],
    [{ ...DEFAULT_OPTIONS, languages: "nonsense!" }, null, { languages: ["en"] }],
  ] as const)("askRequest %#", (options, parent, expected) => {
    expect(askRequest("  Tea?  ", options, parent)).toMatchObject({
      question: "Tea?",
      ...expected,
    });
  });
});

describe("plans", () => {
  const q = (text: string) => ({ q: text, language: "en" });
  it.each([
    [[q("tea")], false, null],
    [[q("  ")], false, "Keep at least one search."],
    [[q("  ")], true, null],
    [Array.from({ length: 7 }, (_, n) => q(`q${n}`)), false, "At most 6 searches."],
    [[q("x".repeat(201))], false, "Keep each search under 200 characters."],
  ])("planProblem %#", (queries, refining, expected) => {
    expect(planProblem(queries, refining)).toBe(expected);
  });

  it("cleanQueries trims and drops blanks", () => {
    expect(cleanQueries([q(" a "), q(""), q("b")])).toEqual([q("a"), q("b")]);
  });
});

describe("format", () => {
  const now = new Date("2026-10-13T12:00:00Z");
  it.each([
    ["2026-10-13T11:59:50Z", "just now"],
    ["2026-10-13T11:58:00Z", "2 minutes ago"],
    ["2026-10-13T09:00:00Z", "3 hours ago"],
    ["2026-10-12T12:00:00Z", "1 day ago"],
    ["not a date", ""],
    [null, ""],
  ])("timeAgo(%j)", (iso, expected) => {
    expect(timeAgo(iso, now)).toBe(expected);
  });

  it.each([
    [1, "1 source"],
    [2, "2 sources"],
    [0, "0 sources"],
  ])("plural(%i)", (n, expected) => {
    expect(plural(n, "source")).toBe(expected);
  });

  it.each([
    ["research-inbox/song-tea", "song-tea"],
    ["https://www.museum.example/tea", "museum.example"],
  ])("slugOf / siteOf %j", (input, expected) => {
    expect(input.startsWith("http") ? siteOf(input) : slugOf(input)).toBe(expected);
  });
});

describe("resolveTarget", () => {
  it.each([
    ["song/characters/lin", { db: "song", col: "characters", id: "lin" }],
    ["characters/lin", { db: "here", col: "characters", id: "lin" }],
    ["characters/lin|Lin", { db: "here", col: "characters", id: "lin" }],
    ["lin", null],
  ])("%j", (target, expected) => {
    expect(resolveTarget(target, "here")).toEqual(expected);
  });
});
