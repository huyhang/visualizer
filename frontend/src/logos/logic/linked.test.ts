import { isLinked, withArticle, withoutArticle } from "./linked";

const lin = { database: "ember", collection: "characters", id: "lin" };
const tea = { database: "ember", collection: "research", id: "tea" };

describe("the articles linked to a section", () => {
  it("adds one last, once, keeping only its reference", () => {
    const titled = { ...lin, title: "Lin Qingyu", missing: false };
    expect(withArticle([tea], titled)).toEqual([tea, lin]);
    expect(withArticle([titled, tea], lin)).toEqual([lin, tea]);
  });

  it("takes one off and leaves the rest in order", () => {
    expect(withoutArticle([tea, lin], tea)).toEqual([lin]);
    expect(withoutArticle([lin], tea)).toEqual([lin]);
  });

  it("knows an article by all three parts of its reference", () => {
    expect(isLinked([lin], { ...lin })).toBe(true);
    expect(isLinked([lin], { ...lin, database: "other" })).toBe(false);
  });
});
