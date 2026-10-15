import { rank, score, type Searchable } from "./search";

const exchange = { label: "The Harbor Exchange", hint: "Scene" };
const road = { label: "The Knight's Road", hint: "Thread" };
const harbour = { label: "Harbor watch", hint: "Goal" };

describe("score", () => {
  it.each<[string, Searchable, string, boolean]>([
    ["an empty query matches everything", road, "", true],
    ["words in any order", exchange, "exchange harbor", true],
    ["a prefix of a word", exchange, "har ex", true],
    ["a word buried inside another", road, "night", true],
    ["the hint as a last resort", road, "thread", true],
    ["a word that is nowhere", road, "dragon", false],
    ["one word of two missing", exchange, "harbor dragon", false],
  ])("%s", (_, item, query, matches) => {
    expect(score(item, query) > 0).toBe(matches);
  });

  it("prefers a label that starts with the word to one that contains it", () => {
    expect(score(harbour, "harbor")).toBeGreaterThan(score(exchange, "harbor"));
  });

  it("prefers a word start to a buried match", () => {
    expect(score(road, "road")).toBeGreaterThan(score(road, "oad"));
  });
});

describe("rank", () => {
  it("orders by how well each answers, dropping what does not", () => {
    expect(rank([exchange, road, harbour], "harbor")).toEqual([harbour, exchange]);
  });

  it("keeps the given order on a tie, and honours the limit", () => {
    expect(rank([road, exchange, harbour], "", 2)).toEqual([road, exchange]);
  });
});
