// An HTTP error from Logos, which answers `{"error": "<sentence>", "code": ...}`.

export class LogosApiError extends Error {
  readonly status: number;
  readonly code: string | null;
  readonly retryAfter: number | null;

  constructor(
    status: number,
    message: string,
    code: string | null = null,
    retryAfter: number | null = null,
  ) {
    super(message);
    this.name = "LogosApiError";
    this.status = status;
    this.code = code;
    this.retryAfter = retryAfter;
  }

  get isConflict(): boolean {
    return this.status === 409;
  }

  get isBusy(): boolean {
    return this.status === 429;
  }
}

/** A sentence for the writer, whatever was thrown. */
export function messageOf(error: unknown, fallback = "Something went wrong."): string {
  return error instanceof Error && error.message ? error.message : fallback;
}

/** What autosave makes of a failed save: someone else's newer copy, a refusal, or no network. */
export function saveFailure(error: unknown): "conflict" | "invalid" | "offline" {
  if (error instanceof LogosApiError) {
    if (error.status === 409) return "conflict";
    if (error.status >= 400 && error.status < 500) return "invalid";
  }
  return "offline";
}
