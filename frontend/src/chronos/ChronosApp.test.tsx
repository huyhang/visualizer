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
