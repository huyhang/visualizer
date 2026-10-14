// An HTTP error from Akasha, which always answers `{"error": "<sentence>"}`.

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }

  get isConflict(): boolean {
    return this.status === 409;
  }

  get isNotFound(): boolean {
    return this.status === 404;
  }

  get isForbidden(): boolean {
    return this.status === 403;
  }

  get isBusy(): boolean {
    return this.status === 429;
  }
}

/** A sentence for the writer, whatever was thrown. */
export function messageOf(error: unknown): string {
  if (error instanceof ApiError && error.isForbidden) return permissionMessage(error);
  if (error instanceof Error && error.message) return error.message;
  return "Something went wrong.";
}

// Akasha words a refusal as "You do not have '<perm>' permission on ...".
const PERMISSION = /'(\w+)' permission/;

/** A refusal in the writer's terms: what access they lack, and who can give it. */
function permissionMessage(error: ApiError): string {
  const permission = PERMISSION.exec(error.message)?.[1];
  const what = permission ? `${permission} access to` : "access to";
  return `You need ${what} this world's research for that. Ask the world's owner to share it with you.`;
}

/** Whether the studio cannot see this world's research at all. */
export function isNoAccess(error: unknown): boolean {
  return error instanceof ApiError && (error.isForbidden || error.isNotFound);
}
