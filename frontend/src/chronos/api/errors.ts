// An HTTP error from Chronos, which answers
// `{"error": "<sentence>", "code": "PLOTLINE_IN_USE", "evidence": {...}}`.
// The code is what the page branches on; the evidence is what it explains with.

export class ChronosApiError extends Error {
  readonly status: number;
  readonly code: string | null;
  readonly evidence: Record<string, unknown>;

  constructor(
    status: number,
    message: string,
    code: string | null = null,
    evidence: Record<string, unknown> = {},
  ) {
    super(message);
    this.name = "ChronosApiError";
    this.status = status;
    this.code = code;
    this.evidence = evidence;
  }

  get isConflict(): boolean {
    return this.status === 409;
  }

  get isForbidden(): boolean {
    return this.status === 403;
  }

  get isNotFound(): boolean {
    return this.status === 404;
  }

  /** Someone saved this record since it was read: the If-Match was stale. */
  get isStale(): boolean {
    return this.code === "REVISION_CONFLICT";
  }
}

/**
 * A refusal that will not change if asked again: the record is gone or is not
 * this reader's to see. Worth neither a retry nor showing what was cached.
 */
export function isFinal(error: unknown): boolean {
  return error instanceof ChronosApiError && error.status >= 400 && error.status < 500;
}

/** The record has gone, or the reader's access to it has: whatever was cached is no answer. */
export function isGone(error: unknown): boolean {
  return error instanceof ChronosApiError && (error.isForbidden || error.isNotFound);
}

/** A sentence for the writer, whatever was thrown. */
export function messageOf(error: unknown, fallback = "Something went wrong."): string {
  return error instanceof Error && error.message ? error.message : fallback;
}

/** The refusal's code, when it is one of ours. */
export function codeOf(error: unknown): string | null {
  return error instanceof ChronosApiError ? error.code : null;
}

/** Ids a refusal's evidence names under `key` -- the threads in the way, say. */
export function evidenceIds(error: unknown, key: string): string[] {
  if (!(error instanceof ChronosApiError)) return [];
  const value = error.evidence[key];
  return Array.isArray(value)
    ? value.filter((v): v is string => typeof v === "string")
    : [];
}
