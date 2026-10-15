import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithDeps } from "../../test/renderChronos";
import { TypeAhead } from "./TypeAhead";

describe("the type-ahead", () => {
  it.each([
    ["finds nothing", () => [], "Nothing matches."],
    [
      "fails",
      () => Promise.reject(new Error("offline")),
      "Could not search — try again in a moment.",
    ],
  ])("says so when its search %s", async (_, search, said) => {
    renderWithDeps(
      <TypeAhead
        label="Find a scene"
        placeholder="Find…"
        search={search}
        onPick={() => {}}
      />,
    );
    await userEvent.type(screen.getByRole("combobox", { name: "Find a scene" }), "x");
    expect(await screen.findByText(said)).toBeInTheDocument();
  });
});
