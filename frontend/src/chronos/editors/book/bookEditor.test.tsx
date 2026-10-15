import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { fakeApi } from "../../test/fakeApi";
import { renderWorkspace } from "../../test/renderChronos";

describe("the book editor", () => {
  it("creates a book, taking the only world, and goes straight into it", async () => {
    const { api, location } = renderWorkspace("#/");
    await userEvent.click(await screen.findByRole("button", { name: "New book" }));
    await userEvent.type(await screen.findByLabelText("Title"), "The Salt Road");
    expect(screen.getByLabelText("Id")).toHaveValue("the-salt-road");
    await userEvent.click(screen.getByRole("button", { name: "Create book" }));
    await waitFor(() => expect(api.callsTo("createBook")).toHaveLength(1));
    expect(api.callsTo("createBook")[0]).toEqual([
      "the-salt-road",
      { title: "The Salt Road", overview: "", calendars: [], world: "ember-pact" },
    ]);
    await waitFor(() => expect(location.current()).toBe("#/the-salt-road"));
  });

  it("attaches a calendar from the library to a new book", async () => {
    const { api } = renderWorkspace("#/");
    await userEvent.click(await screen.findByRole("button", { name: "New book" }));
    await userEvent.type(await screen.findByLabelText("Title"), "Salt");
    await userEvent.click(screen.getByRole("button", { name: "Add a calendar" }));
    await userEvent.selectOptions(
      screen.getByLabelText("Library calendar"),
      "mara/imperial",
    );
    await userEvent.click(screen.getByRole("button", { name: "Create book" }));
    await waitFor(() => expect(api.callsTo("createBook")).toHaveLength(1));
    const body = api.callsTo("createBook")[0]?.[1] as { calendars: unknown[] };
    expect(body.calendars).toEqual([
      {
        id: "imperial-reckoning",
        label: "Imperial Reckoning",
        source: { owner: "mara", calendar: "imperial", rev: null },
        from_tick: null,
        until_tick: null,
        origin: null,
      },
    ]);
  });

  it("saves settings as a full replace, resending every field with the revision", async () => {
    const { api } = renderWorkspace("#/ember-pact");
    await userEvent.click(await screen.findByRole("button", { name: "Book settings" }));
    const title = await screen.findByLabelText("Title");
    await userEvent.clear(title);
    await userEvent.type(title, "The Ember Pact, Revised");
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(api.callsTo("updateBook")).toHaveLength(1));
    const [id, body, rev] = api.callsTo("updateBook")[0] as [
      string,
      Record<string, unknown>,
      number,
    ];
    expect(id).toBe("ember-pact");
    expect(rev).toBe(2);
    expect(body).toEqual({
      title: "The Ember Pact, Revised",
      overview: "A seal, a road and a crown.",
      world: "ember-pact",
      terminus: "coronation",
      calendars: [
        expect.objectContaining({
          id: "imperial",
          source: { owner: "mara", calendar: "imperial", rev: 1 },
        }),
        expect.objectContaining({
          id: "earth",
          source: { owner: "mara", calendar: "earth", rev: 1 },
        }),
      ],
    });
  });

  it("deletes the book only once its id is typed, then returns to the shelf", async () => {
    const { api, location } = renderWorkspace("#/ember-pact");
    await userEvent.click(await screen.findByRole("button", { name: "Book settings" }));
    await userEvent.click(await screen.findByRole("button", { name: "Delete book" }));
    expect(
      await screen.findByText(/This deletes 3 plotlines and 6 scenes/),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Delete this book" }));
    expect(api.callsTo("deleteBook")).toHaveLength(0);
    await userEvent.type(screen.getByLabelText("Book id"), "ember-pact");
    const before = api.calls.length;
    await userEvent.click(screen.getByRole("button", { name: "Delete this book" }));
    await waitFor(() => expect(api.callsTo("deleteBook")).toEqual([["ember-pact", 2]]));
    await waitFor(() => expect(location.current()).toBe("#/"));
    await screen.findByRole("heading", { name: "Your books" });
    // Nothing asks about the book once it has gone.
    const after = api.calls.slice(before).filter((c) => c.method !== "deleteBook");
    expect(after.filter((c) => c.args[0] === "ember-pact")).toEqual([]);
  });

  it("drops the editing controls once the reader's access is withdrawn", async () => {
    const { api, client } = renderWorkspace("#/ember-pact");
    expect(
      await screen.findByRole("button", { name: "Book settings" }),
    ).toBeInTheDocument();
    api.refuse("getBook", 403, "FORBIDDEN");
    await act(() => client.invalidateQueries());
    await waitFor(() =>
      expect(
        screen.queryByRole("button", { name: "Book settings" }),
      ).not.toBeInTheDocument(),
    );
    expect(screen.queryByRole("button", { name: "New thread" })).not.toBeInTheDocument();
  });

  it("offers no settings to a reader without write access", async () => {
    const api = fakeApi();
    api.books = [{ ...api.books[0]!, permissions: { write: false, delete: false } }];
    renderWorkspace("#/ember-pact", api);
    await screen.findAllByRole("link", { name: /The Knight's Road/ });
    expect(screen.queryByRole("button", { name: "Book settings" })).not.toBeInTheDocument();
  });
});
