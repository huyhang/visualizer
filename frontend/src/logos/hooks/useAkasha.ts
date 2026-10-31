// The Akasha tab's subject: nothing yet, words the writer is looking up, an
// article linked to the section, or a phrase linked in the prose. Lookups go through the permission-filtered entity
// search, which prefers the book's own world.

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import type { ArticleRef } from "../doc/types";
import type { MentionAt } from "../editor/mentions";
import { useDeps } from "../deps";

export type AkashaSubject =
  | { kind: "idle" }
  | { kind: "lookup"; text: string }
  | { kind: "linked"; ref: ArticleRef }
  | { kind: "mention"; mention: MentionAt };

/** Words as a lookup query: whitespace collapsed; null when empty or too long to be a name. */
export function lookupText(selected: string): string | null {
  const text = selected.replace(/\s+/g, " ").trim();
  return text && text.length <= 200 ? text : null;
}

export function useAkasha(book: string) {
  const { api } = useDeps();
  const [subject, setSubject] = useState<AkashaSubject>({ kind: "idle" });
  const query = subject.kind === "lookup" ? subject.text : null;
  const results = useQuery({
    queryKey: ["entities", book, query],
    queryFn: () => api.entities(book, query as string),
    enabled: query !== null,
    staleTime: 30_000,
  });
  return { subject, setSubject, results };
}

export type Akasha = ReturnType<typeof useAkasha>;
