// The Akasha articles linked to the open section as a whole. Linking one is a
// change to the section, not to its words: nothing in the prose is marked.

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import type { SectionAddress } from "../api/LogosApi";
import type { Entity, LinkedArticle } from "../api/types";
import type { ArticleRef } from "../doc/types";
import { useDeps } from "../deps";
import { isLinked, refOf, withArticle, withoutArticle } from "../logic/linked";

export function useLinkedArticles(
  at: SectionAddress,
  /** Save the section's list; false if the words could not be saved first. */
  save: (articles: ArticleRef[]) => Promise<boolean>,
) {
  const { api } = useDeps();
  const client = useQueryClient();
  const key = ["linked-articles", at.book, at.volume, at.section];
  const linked = useQuery({ queryKey: key, queryFn: () => api.linkedArticles(at) });
  const [busy, setBusy] = useState(false);
  const rows = linked.data ?? [];

  /** Save `next`, showing it at once with what is already known of each. */
  const change = async (next: ArticleRef[], known: LinkedArticle[]) => {
    setBusy(true);
    try {
      if (!(await save(next)))
        throw new Error("Your words could not be saved, so the link was not changed.");
      // `known` is the list as it was, plus any article just linked, last.
      client.setQueryData<LinkedArticle[]>(key, () =>
        known.filter((row) => isLinked(next, row)),
      );
    } finally {
      setBusy(false);
      // A refused save may mean another tab changed the list: read it again.
      void client.invalidateQueries({ queryKey: key });
    }
  };

  return {
    linked,
    busy,
    isLinked: (ref: ArticleRef) => isLinked(rows, ref),
    link: (article: Entity) =>
      change(withArticle(rows, article), [
        ...rows,
        {
          ...refOf(article),
          database_title: article.database_title,
          collection_title: article.collection_title,
          title: article.title,
          fields: article.fields ?? [],
          missing: false,
        },
      ]),
    unlink: (ref: ArticleRef) => change(withoutArticle(rows, ref), rows),
  };
}

export type LinkedArticles = ReturnType<typeof useLinkedArticles>;
