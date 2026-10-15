// What a screen shows while its data is on the way, or when it did not come.

import type { ReactNode } from "react";
import { isGone, messageOf } from "../../api/errors";
import { Button } from "../../../components/ui/Button";
import { EmptyState } from "../../../components/ui/EmptyState";
import { Skeleton } from "../../../components/ui/Skeleton";

interface QueryLike<T> {
  data: T | undefined;
  error: unknown;
  isPending: boolean;
  refetch: () => unknown;
}

/**
 * Render `children(data)` once it is here; a skeleton before, an explanation
 * on failure. A failed re-read leaves what was shown -- unless it says the
 * record is gone or no longer readable, when the cached copy is no answer.
 */
export function QueryState<T>({
  query,
  lines = 4,
  children,
}: {
  query: QueryLike<T>;
  lines?: number;
  children: (data: T) => ReactNode;
}) {
  if (query.data !== undefined && !isGone(query.error)) return <>{children(query.data)}</>;
  if (query.error) return <LoadError error={query.error} onRetry={() => query.refetch()} />;
  return (
    <div className="cw-loading" role="status" aria-label="Loading">
      <Skeleton lines={lines} />
    </div>
  );
}

export function LoadError({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  return (
    <EmptyState
      icon="alert"
      title="This did not load"
      action={
        onRetry ? (
          <Button size="sm" onClick={onRetry}>
            Try again
          </Button>
        ) : undefined
      }
    >
      {messageOf(error)}
    </EmptyState>
  );
}
