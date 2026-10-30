import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { WriterScene, WriterSceneCards } from "../../api/types";
import { memoryStore } from "../../logic/preferences";
import { AT } from "../../test/fakeApi";
import { renderWriter } from "../../test/renderWriter";

const LYRA = { database: "ember", collection: "characters", id: "lyra", title: "Lyra" };

function scene(id: string, title: string, patch: Partial<WriterScene> = {}): WriterScene {
  return {
    id,
    title,
    when: "Day 5",
    missing: false,
    description: "",
    place: null,
    cast: [],
    unseen: 0,
    ...patch,
  };
}

const CARDS: WriterSceneCards = {
  book: AT.book,
  volume: AT.volume,
  sections: [
    {
      section: "gate",
      scenes: [
        scene("opening", "The gate opens", {
          description: "Lyra reaches the gate at dusk.",
          place: { database: "ember", collection: "places", id: "gate", title: "The Gate" },
          cast: [LYRA],
          unseen: 1,
        }),
        scene("ambush", "Ambush at the ford", { when: "Day 6" }),
      ],
    },
    { section: "tea", scenes: [scene("tea", "Tea with the envoy", { when: "Day 9" })] },
  ],
};

async function opened(setup: Parameters<typeof renderWriter>[0] = {}) {
  const view = renderWriter(setup);
  await screen.findByRole("textbox", { name: "Edit The Gate" });
  const strip = await screen.findByRole("region", { name: "Scenes" });
  return { ...view, strip, user: userEvent.setup() };
}

describe("the scene strip", () => {
  it("opens on this chapter's scene: when, where, who and what happens", async () => {
    const { strip } = await opened({ state: { sceneCards: CARDS } });

    expect(within(strip).getByText("The gate opens")).toBeInTheDocument();
    expect(within(strip).getByText("Day 5")).toBeInTheDocument();
    expect(within(strip).getByRole("button", { name: "The Gate" })).toBeInTheDocument();
    expect(within(strip).getByText("Lyra reaches the gate at dusk.")).toBeInTheDocument();
    expect(within(strip).getByRole("button", { name: "Lyra" })).toBeInTheDocument();
    expect(within(strip).getByText("+1 you can't open")).toBeInTheDocument();
    expect(within(strip).getByText("This chapter · scene 1 of 2")).toBeInTheDocument();
    expect(within(strip).getByText("1 of 3")).toBeInTheDocument();
    // Nothing comes before the first chapter's first scene.
    expect(within(strip).getByRole("button", { name: "Previous scene" })).toBeDisabled();
  });

  it("steps on to the next chapter's scene, and goes to write it", async () => {
    const { strip, user, deps } = await opened({ state: { sceneCards: CARDS } });

    await user.click(within(strip).getByRole("button", { name: "Next scene" }));
    expect(within(strip).getByText("2 of 3")).toBeInTheDocument();
    await user.click(within(strip).getByRole("button", { name: "Next scene" }));
    expect(within(strip).getByText("3 of 3")).toBeInTheDocument();
    expect(within(strip).getByRole("button", { name: "Next scene" })).toBeDisabled();

    await user.click(within(strip).getByRole("button", { name: /Chapter 2/ }));
    await waitFor(() => expect(deps.navigate).toHaveBeenCalledWith("/write/one/tea"));
  });

  it("opens a name in Akasha, in a new tab", async () => {
    const { strip, user, deps } = await opened({ state: { sceneCards: CARDS } });

    await user.click(within(strip).getByRole("button", { name: "Lyra" }));

    expect(deps.openTab).toHaveBeenCalledWith("/akasha/#/ember/characters/lyra");
  });

  it("links a chapter that tells no scene yet to the ones it does", async () => {
    const { strip, user, api } = await opened({
      state: {
        sceneChoices: [
          { id: "opening", title: "The gate opens", when: "Day 5", missing: false },
          { id: "ambush", title: "Ambush at the ford", when: "Day 6", missing: false },
        ],
      },
    });
    expect(within(strip).getByText(/No Chronos scene is linked/)).toBeInTheDocument();

    await user.click(within(strip).getByRole("button", { name: "Link scenes" }));
    const dialog = await screen.findByRole("dialog", { name: "Scenes in The Gate" });
    await user.click(within(dialog).getByRole("checkbox", { name: /Ambush at the ford/ }));
    await user.click(within(dialog).getByRole("checkbox", { name: /The gate opens/ }));
    await user.click(within(dialog).getByRole("button", { name: "Save" }));

    // In story order, whatever order they were ticked in.
    expect(api.updateSectionScenes).toHaveBeenCalledWith(AT, ["opening", "ambush"], 5);
    expect(await within(strip).findByText("The gate opens")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("folds away to one line, and stays folded next time", async () => {
    const store = memoryStore();
    const first = await opened({ state: { sceneCards: CARDS }, store });

    await first.user.click(within(first.strip).getByRole("button", { name: /Scenes/ }));

    expect(within(first.strip).queryByText("Lyra reaches the gate at dusk.")).toBeNull();
    expect(within(first.strip).getByText("The gate opens · Day 5 +1")).toBeInTheDocument();
    first.unmount();

    const again = await opened({ state: { sceneCards: CARDS }, store });
    expect(
      within(again.strip).getByRole("button", { name: /Scenes/, expanded: false }),
    ).toBeInTheDocument();
  });
});
