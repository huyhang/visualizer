import { ChronosApiError } from "./api/errors";
import { defaultQueryClient, signedOut } from "./ChronosApp";

describe("signedOut", () => {
  it.each<[unknown, boolean]>([
    [new ChronosApiError(401, "Sign in."), true],
    [new ChronosApiError(403, "Not yours."), false],
    [new Error("offline"), false],
  ])("%s", (error, expected) => {
    expect(signedOut(error)).toBe(expected);
  });
});

describe("the page's retry rule", () => {
  const retry = defaultQueryClient().getDefaultOptions().queries?.retry as (
    count: number,
    error: unknown,
  ) => boolean;

  it.each<[string, number, unknown, boolean]>([
    ["a dropped connection, once", 0, new TypeError("Failed to fetch"), true],
    ["a server error, once", 0, new ChronosApiError(500, "Boom."), true],
    ["nothing twice", 1, new ChronosApiError(500, "Boom."), false],
    ["no refusal", 0, new ChronosApiError(403, "Not yours."), false],
    ["no record that has gone", 0, new ChronosApiError(404, "No such scene."), false],
    ["no lapsed session", 0, new ChronosApiError(401, "Sign in."), false],
  ])("asks again for %s", (_, count, error, expected) => {
    expect(retry(count, error)).toBe(expected);
  });
});

describe("defaultQueryClient", () => {
  it("sends the writer to sign in when a read finds the session gone", async () => {
    const signIn = vi.fn();
    const client = defaultQueryClient(signIn);
    await client
      .fetchQuery({
        queryKey: ["x"],
        queryFn: () => Promise.reject(new ChronosApiError(401, "Sign in.")),
        retry: false,
      })
      .catch(() => {});
    expect(signIn).toHaveBeenCalledOnce();
  });

  it("leaves any other failure to the screen", async () => {
    const signIn = vi.fn();
    const client = defaultQueryClient(signIn);
    await client
      .fetchQuery({
        queryKey: ["y"],
        queryFn: () => Promise.reject(new ChronosApiError(500, "Boom.")),
        retry: false,
      })
      .catch(() => {});
    expect(signIn).not.toHaveBeenCalled();
  });
});
