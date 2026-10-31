// The Akasha articles a section links to as a whole: adding one, taking one
// off. The list is the section's, kept in the order the writer linked them.

import type { ArticleRef } from "../doc/types";

/** Just the reference, whatever else the value carries -- a title, fields. */
export function refOf({ database, collection, id }: ArticleRef): ArticleRef {
  return { database, collection, id };
}

export function sameArticle(a: ArticleRef, b: ArticleRef): boolean {
  return a.database === b.database && a.collection === b.collection && a.id === b.id;
}

export function isLinked(list: readonly ArticleRef[], ref: ArticleRef): boolean {
  return list.some((item) => sameArticle(item, ref));
}

/** The list with `ref` added last, or unchanged if it is already there. */
export function withArticle(list: readonly ArticleRef[], ref: ArticleRef): ArticleRef[] {
  const refs = list.map(refOf);
  return isLinked(refs, ref) ? refs : [...refs, refOf(ref)];
}

export function withoutArticle(list: readonly ArticleRef[], ref: ArticleRef): ArticleRef[] {
  return list.filter((item) => !sameArticle(item, ref)).map(refOf);
}
