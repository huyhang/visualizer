// Everything the writing page needs before it can show a word: the
// manuscript (for the outline and permissions), the section, its drafts, the
// open draft, and whatever this device kept of words not yet saved.

import { useQuery } from "@tanstack/react-query";
import type { LogosApi, SectionAddress } from "../api/LogosApi";
import type { Draft, DraftListing, Manuscript, Section } from "../api/types";
import { useDeps } from "../deps";
import { chooseDraft } from "../logic/drafts";
import { findSection } from "../logic/outline";
import { recoveryKey, type RecoveryStore, type RecoverySnapshot } from "../logic/recovery";
import type { Route } from "../logic/route";

export interface Workspace {
  manuscript: Manuscript;
  at: SectionAddress;
  section: Section;
  listing: DraftListing;
  draft: Draft;
  recovered: RecoverySnapshot | null;
}

export type Loaded =
  { kind: "ready"; workspace: Workspace } | { kind: "read-only"; at: SectionAddress };

export class SectionNotFound extends Error {
  constructor() {
    super(
      "This section is not in the manuscript any more. It may have been moved or deleted.",
    );
    this.name = "SectionNotFound";
  }
}

/** The load itself, apart from React, so a test can call it with fakes. */
export async function loadWorkspace(
  api: LogosApi,
  recovery: RecoveryStore,
  user: string,
  route: Route,
): Promise<Loaded> {
  const manuscript = await api.manuscript(route.book);
  const located = findSection(manuscript, route.volume, route.section);
  if (!located) throw new SectionNotFound();
  const at = { book: route.book, volume: located.volume.id, section: located.section.id };
  if (!manuscript.permissions.write) return { kind: "read-only", at };
  const [section, listing] = await Promise.all([api.section(at), api.drafts(at)]);
  const row = chooseDraft(listing.drafts, route.draft);
  if (!row) throw new SectionNotFound();
  const draft = await api.draft(at, row.id);
  const recovered = await recovery
    .get(recoveryKey({ user, ...at, draft: draft.id }))
    .catch(() => null);
  return {
    kind: "ready",
    workspace: { manuscript, at, section, listing, draft, recovered },
  };
}

export function useWorkspace(route: Route) {
  const { api, recovery, user } = useDeps();
  return useQuery({
    queryKey: ["workspace", route.book, route.volume, route.section, route.draft],
    queryFn: () => loadWorkspace(api, recovery, user, route),
    staleTime: Infinity,
    gcTime: Infinity,
    refetchOnWindowFocus: false,
    retry: false,
  });
}
