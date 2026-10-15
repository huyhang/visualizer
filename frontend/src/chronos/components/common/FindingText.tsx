// A finding's message, with the articles it quotes by id read as their titles.

import { useQueries } from "@tanstack/react-query";
import type { EntityRef } from "../../api/types";
import { useApi } from "../../deps";
import { keys } from "../../hooks/queries";
import { withTitles } from "../../logic/findings";
import { entityTitle } from "./EntityName";

export function FindingText({
  book,
  message,
  refs,
}: {
  book: string;
  message: string;
  refs: EntityRef[];
}) {
  const api = useApi();
  const articles = useQueries({
    queries: refs.map((r) => ({
      queryKey: keys.entity(book, r.database, r.collection, r.id),
      queryFn: () => api.getEntity(book, r.database, r.collection, r.id),
      staleTime: 5 * 60_000,
    })),
  });
  const titles = new Map(
    refs.map((r, n) => [r.id, entityTitle(articles[n]?.data?.document, r.id)] as const),
  );
  return <>{withTitles(message, titles)}</>;
}
