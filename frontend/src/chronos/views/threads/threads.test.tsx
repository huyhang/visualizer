import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { Book } from "../../api/types";
import { fakeApi } from "../../test/fakeApi";
import { book } from "../../test/fixtures";
import { renderWorkspace } from "../../test/renderChronos";
import { sortedBooks } from "../books/BooksView";

describe("the threads screen", () => {
  it("lists each thread with its goals and health", async () => {
    renderWorkspace("#/ember-pact");
    const road = (await screen.findByRole("link", { name: /The Knight's Road/ })).closest(
      "li",
    ) as HTMLElement;
    expect(
      within(road).getByRole("button", { name: /Deliver the Ember Seal/ }),
    ).toBeInTheDocument();
    expect(within(road).getByText("1 problem")).toBeInTheDocument();
    expect(screen.getByText("Page 1 of 1 · 3 threads")).toBeInTheDocument();
  });

  it("filters on the server as you type", async () => {
    const { api } = renderWorkspace("#/ember-pact");
    await screen.findByRole("link", { name: /The Knight's Road/ });
    await userEvent.type(screen.getByRole("searchbox", { name: "Filter threads" }), "spy");
    expect(await screen.findByText("Page 1 of 1 · 1 thread")).toBeInTheDocument();
    expect(api.callsTo("listPlotlines").at(-1)?.[1]).toMatchObject({
      filter: "spy",
      page: 1,
    });
  });

  it("opens a goal beside the table instead of leaving it", async () => {
    const { location } = renderWorkspace("#/ember-pact");
    await userEvent.click(
      await screen.findByRole("button", { name: /Deliver the Ember Seal/ }),
    );
    const panel = await screen.findByRole("complementary", { name: "Details" });
    expect(
      await within(panel).findByRole("heading", { name: "Deliver the Ember Seal" }),
    ).toBeInTheDocument();
    expect(location.current()).toBe("#/ember-pact");
  });

  it("glances at a thread in the panel", async () => {
    renderWorkspace("#/ember-pact");
    const [first] = await screen.findAllByRole("button", { name: "Glance at this thread" });
    await userEvent.click(first as HTMLElement);
    const panel = await screen.findByRole("complementary", { name: "Details" });
    expect(
      await within(panel).findByRole("button", { name: /Aldric Departs/ }),
    ).toBeInTheDocument();
  });

  it("says what an empty filter found", async () => {
    renderWorkspace("#/ember-pact");
    await screen.findByRole("link", { name: /The Knight's Road/ });
    await userEvent.type(
      screen.getByRole("searchbox", { name: "Filter threads" }),
      "dragon",
    );
    expect(await screen.findByText("No thread matches")).toBeInTheDocument();
  });
});

describe("the shelf", () => {
  it("offers the report straight from a conflicted book", async () => {
    const { location } = renderWorkspace("#/");
    await userEvent.click(await screen.findByRole("link", { name: "Conflicted" }));
    expect(location.current()).toBe("#/ember-pact/~issues");
  });

  it("invites a first book when there are none", async () => {
    const api = fakeApi();
    api.books = [];
    renderWorkspace("#/", api);
    expect(await screen.findByText("You have no books yet")).toBeInTheDocument();
  });

  it("orders books by title, falling back to the id", () => {
    const books: Book[] = [
      book({ id: "z", title: "Alpha" }),
      book({ id: "b", title: "" }),
      book({ id: "a", title: "Gamma" }),
    ];
    expect(sortedBooks(books).map((b) => b.id)).toEqual(["z", "b", "a"]);
  });
});
