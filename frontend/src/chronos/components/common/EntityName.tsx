// An Akasha article's title, read through Chronos; its id until it arrives,
// and its id still if the article has gone.

import type { EntityRef } from "../../api/types";
import { useEntity } from "../../hooks/queries";

export function entityTitle(
  document: { title?: unknown } | undefined,
  fallback: string,
): string {
  return typeof document?.title === "string" && document.title ? document.title : fallback;
}

export function EntityName({ book, entity }: { book: string; entity: EntityRef }) {
  const { data } = useEntity(book, entity);
  return <>{entityTitle(data?.document, entity.id)}</>;
}
