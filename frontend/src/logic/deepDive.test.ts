import { describe, expect, it } from "vitest";
import { MAX_QUESTION } from "./ask";
import { clip, deepDiveQuestion } from "./deepDive";

describe("clip", () => {
  it.each([
    ["short", 10, "short"],
    ["  spaced   out  ", 20, "spaced out"],
    ["the quick brown fox jumps", 15, "the quick…"],
    ["abcdefghijklmnopqrstuvwxyz", 10, "abcdefghi…"],
    ["ends with a comma, and more", 19, "ends with a comma…"],
  ])("clip(%j, %i) -> %j", (text, limit, expected) => {
    const clipped = clip(text, limit);
    expect(clipped).toBe(expected);
    expect(clipped.length).toBeLessThanOrEqual(limit);
  });
});

describe("deepDiveQuestion", () => {
  it("names the passage and the topic it came from", () => {
    expect(deepDiveQuestion("Jian ware bowls were prized.", "Song tea culture")).toBe(
      "Tell me more about: Jian ware bowls were prized. (in the context of: Song tea culture)",
    );
  });

  it("leaves out an empty context", () => {
    expect(deepDiveQuestion("Bowls", "  ")).toBe("Tell me more about: Bowls");
  });

  it.each([
    ["x ".repeat(400), "y ".repeat(10)],
    ["x ".repeat(400), "y ".repeat(400)],
    ["word ".repeat(1000), ""],
  ])("always fits the box's limit (%#)", (passage, parent) => {
    expect(deepDiveQuestion(passage, parent).length).toBeLessThanOrEqual(MAX_QUESTION);
  });
});
