import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { harness, renderWithDeps, renderWorkspace } from "../../test/renderChronos";
import { BookScope } from "./BookScope";
import { LensProvider, useLens } from "./Lens";

const LYRA = { database: "ember-pact", collection: "characters", id: "lyra" };

function Probe() {
  const lens = useLens();
  const lit = ["departs", "infiltrates", "exchange"].filter((s) => !lens.fades(s));
  return (
    <>
      <output aria-label="lens">{`${lens.subject?.id ?? "nobody"}:${lit.join(",")}`}</output>
      <button type="button" onClick={() => lens.follow(LYRA)}>
        follow lyra
      </button>
    </>
  );
}

describe("the character lens", () => {
  it("fades nothing until someone is followed, then everything they are not in", async () => {
    renderWithDeps(
      <BookScope id="ember-pact">
        <LensProvider>
          <Probe />
        </LensProvider>
      </BookScope>,
      harness("#/ember-pact"),
    );
    expect(screen.getByLabelText("lens")).toHaveTextContent(
      "nobody:departs,infiltrates,exchange",
    );
    await userEvent.click(screen.getByRole("button", { name: "follow lyra" }));
    expect(await screen.findByText("lyra:infiltrates,exchange")).toBeInTheDocument();
  });

  it("is picked from the sidebar and put down with ✕", async () => {
    renderWorkspace("#/ember-pact");
    const picker = await screen.findByRole("combobox", {
      name: "Follow a character, place or thing",
    });
    await screen.findByRole("option", { name: /Sir Aldric · \d+ scenes/ });
    await userEvent.selectOptions(
      picker,
      screen.getByRole("option", { name: /Sir Aldric/ }),
    );
    expect(
      await screen.findByRole("button", { name: "Stop following" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Sir Aldric", { selector: ".cw-lens-name *, .cw-lens-name" }),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Stop following" }));
    expect(
      screen.getByRole("combobox", { name: "Follow a character, place or thing" }),
    ).toBeInTheDocument();
  });
});
