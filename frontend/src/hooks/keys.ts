// Query keys, in one place so a mutation invalidates exactly what it changed.

export const keys = {
  availability: ["availability"] as const,
  jobs: ["jobs"] as const,
  job: (id: string) => ["job", id] as const,
  inbox: ["inbox"] as const,
  drafts: ["draft"] as const,
  draft: (slug: string) => ["draft", slug] as const,
  notes: ["notes"] as const,
  note: (slug: string) => ["note", slug] as const,
};
