import { bookOf, hashFor, parseRoute, segments, to, type Route } from "./route";

describe("parseRoute", () => {
  it.each<[string, Route]>([
    ["", to.books()],
    ["#/", to.books()],
    ["#/~calendars", to.calendars()],
    ["#/ember-pact", to.threads("ember-pact")],
    ["#/ember-pact/", to.threads("ember-pact")],
    ["#/ember-pact/~scenes", to.scenes("ember-pact")],
    ["#/ember-pact/~issues", to.issues("ember-pact")],
    ["#/ember-pact/~goals", to.goals("ember-pact")],
    ["#/ember-pact/~goals/seal", to.goals("ember-pact", "seal")],
    ["#/ember-pact/~map", to.map("ember-pact")],
    ["#/ember-pact/~map/a,b,,c", to.map("ember-pact", ["a", "b", "c"])],
    ["#/ember-pact/road", to.plotline("ember-pact", "road")],
    ["#/ember-pact/road/at/dawn", to.plotline("ember-pact", "road", "dawn")],
    ["#/ember-pact/road/at", to.plotline("ember-pact", "road")],
    ["#/ember-pact/road/connected", to.connected("ember-pact", "road")],
    ["#/ember-pact/road/connected/dawn", to.connected("ember-pact", "road", "dawn")],
    ["#/the%20book/a%2Fb", to.plotline("the book", "a/b")],
  ])("reads %j", (hash, expected) => {
    expect(parseRoute(hash)).toEqual(expected);
  });
});

describe("hashFor", () => {
  it.each<[Route, string]>([
    [to.books(), "#/"],
    [to.calendars(), "#/~calendars"],
    [to.threads("b"), "#/b"],
    [to.scenes("b"), "#/b/~scenes"],
    [to.issues("b"), "#/b/~issues"],
    [to.goals("b"), "#/b/~goals"],
    [to.goals("b", "g"), "#/b/~goals/g"],
    [to.map("b"), "#/b/~map"],
    [to.map("b", ["x", "y z"]), "#/b/~map/x,y%20z"],
    [to.connected("b", "p", "s"), "#/b/p/connected/s"],
    [to.plotline("b", "a/b"), "#/b/a%2Fb"],
    [to.plotline("b", "p", "s"), "#/b/p/at/s"],
  ])("writes %j", (route, expected) => {
    expect(hashFor(route)).toBe(expected);
  });

  it.each<Route>([
    to.books(),
    to.calendars(),
    to.threads("the book"),
    to.goals("b", "g/1"),
    to.map("b", ["a", "b"]),
    // An id holding a comma stays one thread, not two.
    to.map("b", ["a,b", "c"]),
    to.map("b", ["50%", "c"]),
    to.connected("b", "p"),
    to.plotline("b", "p", "s"),
  ])("round-trips %j", (route) => {
    expect(parseRoute(hashFor(route))).toEqual(route);
  });
});

describe("segments", () => {
  it("keeps a malformed escape as typed rather than throwing", () => {
    expect(segments("#/b/%E0%A4%A")).toEqual(["b", "%E0%A4%A"]);
  });
});

describe("bookOf", () => {
  it.each<[Route, string | null]>([
    [to.books(), null],
    [to.calendars(), null],
    [to.issues("b"), "b"],
    [to.plotline("x", "p"), "x"],
  ])("finds the book of %j", (route, expected) => {
    expect(bookOf(route)).toBe(expected);
  });
});
