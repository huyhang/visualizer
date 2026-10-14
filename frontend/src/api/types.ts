// The shapes Akasha's research and document APIs answer with. The reference is
// docs/akasha/openapi.json; these mirror the parts the studio reads.

export type JobState =
  | "submitting"
  | "queued"
  | "running"
  | "awaiting_approval"
  | "importing"
  | "done"
  | "failed"
  | "cancelled";

export type Review = "pending" | "accepted" | "rejected" | "superseded" | "done" | null;

export type Verification = "checked" | "skipped" | "off" | null;

export interface Query {
  q: string;
  language: string;
}

export interface Plan {
  queries: Query[];
  approved: boolean;
  expires_at: string | null;
}

export interface Job {
  id: string;
  world: string;
  requester: string;
  question: string;
  state: JobState;
  progress: { stage?: string; message?: string } | null;
  error: { code: string; message: string } | null;
  created_at: string;
  updated_at: string;
  draft: string | null;
  review: Review;
  accepted: string | null;
  verification: Verification;
  plan: Plan | null;
  refines: string | null;
  superseded_by: string | null;
  parent: string | null;
  notes: string[];
}

export interface InboxRow {
  draft: string;
  title: string;
  question: string;
  requester: string;
  job: string;
  created_at: string;
  verification: Verification;
  facts: number;
  images: number;
  refining: boolean;
}

export interface Citation {
  source: string;
  quote: string;
}

export type FactCheck = "supported" | "partial" | "unchecked";

export interface Fact {
  text: string;
  check: FactCheck;
  citations: Citation[];
}

export interface DroppedFact {
  text: string;
  reason: string;
}

export interface SourceRow {
  key: string;
  ref: string;
  url: string;
  title: string;
  new: boolean;
}

export interface ImageCandidate {
  index: number;
  url: string;
  caption: string;
  license: string | null;
  source: string;
  imported: string | null;
}

export interface VerificationReport {
  status: "checked" | "skipped" | "off";
  model: string | null;
  reason: string | null;
  checked: number;
  removed: number;
}

export interface DocumentResult {
  id: string;
  document: Record<string, unknown>;
  rev: number;
}

export interface Draft {
  draft: string;
  article: DocumentResult;
  job: Job;
  facts: Fact[];
  dropped_facts: DroppedFact[];
  sources: SourceRow[];
  images: ImageCandidate[];
  verification: VerificationReport | null;
  links: string[];
  refining: Job | null;
}

export type AvailabilityState =
  | "off"
  | "unreachable"
  | "misconfigured"
  | "incompatible"
  | "degraded"
  | "queue_full"
  | "busy"
  | "cold"
  | "ready";

export interface Availability {
  state: AvailabilityState;
  can_submit: boolean;
  message: string;
  model: string | null;
  verifier: "up" | "down" | "not_configured" | null;
  private: boolean;
}

export interface AskRequest {
  question: string;
  languages?: string[];
  max_sources?: number;
  include_images?: boolean;
  verify?: "auto" | "required" | "off";
  approve_plan?: boolean;
  parent?: string | null;
}

export interface RefineRequest {
  feedback: string;
  exclude_sources?: string[];
}

export interface NoteRequest {
  title: string;
  body: string;
  note?: string | null;
  rev?: number | null;
  drafts?: string[];
}

export interface NoteSaved {
  note: string;
  rev: number;
  sources: string[];
  relinked: string[];
}

/** A whole draft accepted: the note it became, and where its sources went. */
export interface Accepted {
  article: string;
  sources: string[];
  relinked: string[];
}

export interface NoteSummary {
  id: string;
  title: string;
  rev: number;
  updated: string | null;
}

export interface Media {
  id: string;
  alt?: string;
  thumbnail_url?: string;
  display_url?: string;
}

/** A world, collection and article: the address every Akasha link resolves to. */
export interface ArticleRef {
  db: string;
  col: string;
  id: string;
}
