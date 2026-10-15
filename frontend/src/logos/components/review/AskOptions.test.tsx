import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { vi } from "vitest";
import type { Entity } from "../../api/types";
import { AT } from "../../test/fakeApi";
import { renderWithDeps } from "../../test/renderWriter";
import { AskOptions, type AskSettings } from "./AskOptions";

const DEFAULTS: AskSettings = {
  checks: ["continuity", "anachronism", "prose"],
  verify: "auto",
  dialect: "en-US",
  include: [],
};

const lin: Entity = {
  database: "ember",
  collection: "characters",
  id: "lin",
  title: "Lin Qingyu",
  database_title: "Ember",
  collection_title: "Characters",
};

/** The options as the Editor tab holds them: what changes is kept and reported. */
function setup({
  settings = DEFAULTS,
  saved = true,
}: { settings?: AskSettings; saved?: boolean } = {}) {
  const onChange = vi.fn();
  function Held() {
    const [held, setHeld] = useState(settings);
    return (
      <AskOptions
        at={AT}
        draft="draft-1"
        settings={held}
        onChange={(next) => {
          onChange(next);
          setHeld(next);
        }}
        settled={async () => saved}
      />
    );
  }
  const view = renderWithDeps(<Held />, { state: { entities: [lin] } });
  return { ...view, onChange, user: userEvent.setup() };
}

describe("AskOptions", () => {
  it.each<[string, AskSettings["checks"]]>([
    ["Continuity", ["anachronism", "prose"]],
    ["Anachronism", ["continuity", "prose"]],
    ["Prose", ["continuity", "anachronism"]],
  ])("leaves out the %s check when it is unticked", async (label, checks) => {
    const { onChange, user } = setup();
    await user.click(screen.getByRole("checkbox", { name: new RegExp(label) }));
    expect(onChange).toHaveBeenLastCalledWith({ ...DEFAULTS, checks });
  });

  it("will not untick the last check left", () => {
    setup({ settings: { ...DEFAULTS, checks: ["prose"] } });
    expect(screen.getByRole("checkbox", { name: /Prose/ })).toBeDisabled();
  });

  it.each<[string, string, Partial<AskSettings>]>([
    ["English", "en-GB", { dialect: "en-GB" }],
    ["Second check", "required", { verify: "required" }],
    ["Second check", "off", { verify: "off" }],
  ])("sets %s to %s", async (name, value, patch) => {
    const { onChange, user } = setup();
    await user.selectOptions(screen.getByRole("combobox", { name }), value);
    expect(onChange).toHaveBeenLastCalledWith({ ...DEFAULTS, ...patch });
  });

  it("sends an article found in Akasha, and stops sending it", async () => {
    const { onChange, user } = setup();
    await user.type(
      screen.getByRole("searchbox", { name: "Search Akasha for an article to send" }),
      "Li",
    );
    await user.click(await screen.findByRole("button", { name: /Lin Qingyu/ }));
    expect(onChange).toHaveBeenLastCalledWith({
      ...DEFAULTS,
      include: [{ ref: "ember/characters/lin", title: "Lin Qingyu" }],
    });
    await user.click(screen.getByRole("button", { name: "Stop sending Lin Qingyu" }));
    expect(onChange).toHaveBeenLastCalledWith(DEFAULTS);
  });

  it("shows what the editor will read, and what it is left without and why", async () => {
    const { api, user } = setup();
    await user.click(screen.getByRole("button", { name: "What the editor will read" }));
    expect(await screen.findByText("Song tea")).toBeInTheDocument();
    expect(screen.getByText("Still in the research inbox")).toBeInTheDocument();
    expect(api.reviewReferences).toHaveBeenCalledWith(AT, "draft-1", []);
    expect(screen.queryByText(/not saved yet/)).not.toBeInTheDocument();
  });

  it("says when the words it previews from are not the latest", async () => {
    const { user } = setup({ saved: false });
    await user.click(screen.getByRole("button", { name: "What the editor will read" }));
    expect(await screen.findByText(/latest words are not saved yet/)).toBeInTheDocument();
  });
});
