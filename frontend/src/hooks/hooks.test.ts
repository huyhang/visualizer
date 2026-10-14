import { describe, expect, it } from "vitest";
import { ApiError } from "../api/errors";
import {
  addImage,
  addText,
  emptyComposition,
  setTitle,
  type Composition,
} from "../logic/compose";
import { fakeApi } from "../test/fakeApi";
import { localStore } from "./useComposition";
import { saveComposition } from "./saveComposition";
import { topicFromHash } from "./useSelection";

const IMAGE = { draft: "tea", index: 1, caption: "Bowl", previewUrl: "/p", mediaId: null };

function composition(): Composition {
  let n = 0;
  const newId = () => `b${++n}`;
  return addImage(
    addText(setTitle(emptyComposition(), "Tea"), "Text.", "tea", newId),
    IMAGE,
    newId,
  );
}

type Media = ReadonlyMap<string, string>;

describe("saveComposition", () => {
  it("imports the images, hands back their media ids, then saves", async () => {
    const { api, calls } = fakeApi();
    const handed: Media[] = [];
    const saved = await saveComposition(api, composition(), (m) => handed.push(m));
    expect(calls.map((c) => c.method)).toEqual(["importImage", "saveNote"]);
    expect([...handed[0]!]).toEqual([["b2", "a".repeat(31) + "1"]]);
    expect(calls[1]!.args[0]).toMatchObject({
      title: "Tea",
      drafts: ["research-inbox/tea"],
    });
    expect((calls[1]!.args[0] as { body: string }).body).toContain(
      `{{image:${"a".repeat(31)}1|right|40|Bowl}}`,
    );
    expect(saved.note).toBe("research/new-note");
  });

  it("does not import an image twice", async () => {
    const { api, calls } = fakeApi();
    const comp = composition();
    comp.blocks[1] = {
      ...comp.blocks[1]!,
      mediaId: "c".repeat(32),
    } as Composition["blocks"][number];
    const handed: Media[] = [];
    await saveComposition(api, comp, (m) => handed.push(m));
    expect(calls.map((c) => c.method)).toEqual(["saveNote"]);
    expect(handed).toEqual([]);
  });

  it("a failed save keeps the imports it made", async () => {
    const { api } = fakeApi({}, { saveNote: () => Promise.reject(new Error("stale")) });
    const handed: Media[] = [];
    await expect(
      saveComposition(api, composition(), (m) => handed.push(m)),
    ).rejects.toThrow("stale");
    expect(handed).toHaveLength(1);
  });

  it("a picture that will not import is named, and the ones before it are kept", async () => {
    const second = { ...IMAGE, index: 2, caption: "Kiln" };
    let n = 10;
    const comp = addImage(composition(), second, () => `b${++n}`);
    const { api, calls } = fakeApi(
      {},
      {
        importImage: async (_slug: string, index: number) => {
          if (index === 2) throw new ApiError(502, "The source answered 404");
          return { id: "d".repeat(32) };
        },
      },
    );
    const handed: Media[] = [];
    const failure = await saveComposition(api, comp, (m) => handed.push(m)).catch(
      (e: unknown) => e,
    );
    expect(failure).toBeInstanceOf(ApiError);
    expect((failure as ApiError).status).toBe(502);
    expect((failure as ApiError).message).toBe(
      "The picture “Kiln” could not be imported (The source answered 404). " +
        "Remove it from the note and save again.",
    );
    expect([...handed[0]!]).toEqual([["b2", "d".repeat(32)]]);
    expect(calls.some((c) => c.method === "saveNote")).toBe(false);
  });
});

describe("localStore", () => {
  it("keeps a composition per world", () => {
    const store = localStore("song", window.localStorage);
    store.save(composition());
    expect(store.load()).toEqual(composition());
    expect(localStore("elsewhere", window.localStorage).load()).toBeNull();
  });

  it.each(["not json", '{"blocks": "nope"}', "null"])(
    "survives a damaged entry %j",
    (raw) => {
      window.localStorage.setItem("akasha-studio-note:song", raw);
      expect(localStore("song", window.localStorage).load()).toBeNull();
    },
  );

  it("works without storage at all", () => {
    const store = localStore("song", null);
    store.save(composition());
    expect(store.load()).toBeNull();
  });
});

describe("topicFromHash", () => {
  it.each([
    ["#topic=rj_1", "rj_1"],
    ["#topic=", null],
    ["", null],
    ["#/song", null],
  ])("%j", (hash, expected) => {
    expect(topicFromHash(hash)).toBe(expected);
  });
});
