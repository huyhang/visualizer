// The shapes Logos answers with, as far as the writing page reads them
// (docs/logos/openapi.json is the whole contract).

import type { ArticleRef, LogosDocument } from "../doc/types";

export type SectionKind = "chapter" | "prologue" | "epilogue" | "glossary";

export interface SectionSummary {
  id: string;
  volume: string;
  kind: SectionKind;
  number: number | null;
  title: string | null;
  primary_draft_id: string;
  rev: number;
}

export interface Section extends SectionSummary {
  document: LogosDocument;
}

export interface VolumeSummary {
  id: string;
  number: number;
  title: string;
  sections: SectionSummary[];
}

export interface SectionAlias {
  source_volume: string;
  section: string;
  target_volume: string;
}

export interface Manuscript {
  book: string;
  title: string;
  world: string | null;
  rev: number;
  volumes: VolumeSummary[];
  section_aliases?: SectionAlias[];
  permissions: { read: boolean; write: boolean };
}

export interface DraftRow {
  id: string;
  name: string;
  primary: boolean;
  rev: number;
  word_count?: number;
}

export interface Draft extends DraftRow {
  document: LogosDocument;
  section_rev?: number;
}

export interface DraftListing {
  drafts: DraftRow[];
  section_rev: number;
}

// -- Akasha lookup ---------------------------------------------------------------

export interface Entity extends ArticleRef {
  title: string;
  database_title: string;
  collection_title: string;
  fields?: { name: string; value: string }[];
}

// -- the Writing Coach -------------------------------------------------------------

export interface CoachIssue {
  id: string;
  block: string;
  category: string;
  title: string;
  message: string;
  excerpt: string;
  replacement: string | null;
}

export interface CoachReview {
  dialect: string;
  issues: CoachIssue[];
}

// -- LLM review --------------------------------------------------------------------

export type Dialect = "en-US" | "en-GB";
export type Check = "continuity" | "anachronism" | "prose";
export type VerifyMode = "auto" | "required" | "off";

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
  verifier: string | null;
  private: boolean;
}

export interface Progress {
  stage: string;
  message?: string;
}

export interface JobError {
  code: string;
  message: string;
}

export type ReviewState = "queued" | "running" | "done" | "failed" | "cancelled";
export type IssueStatus = "open" | "dismissed" | "resolved";
export type Stance = "maintains" | "revises" | "withdraws";

export interface Turn {
  role: "writer" | "editor";
  text: string;
  at: string | null;
  stance: Stance | null;
  suggestion: string | null;
  replacement: string | null;
  model: string | null;
}

export interface Reply {
  state: ReviewState;
  progress: Progress | null;
  error: JobError | null;
}

export interface ReviewIssue {
  id: string;
  check: Check;
  severity: "info" | "warning";
  confidence: "possible" | "likely";
  block: string;
  quote: string;
  message: string;
  suggestion: string | null;
  replacement: string | null;
  reference: string | null;
  verified: boolean | null;
  status: IssueStatus;
  dismissed_before: string | null;
  discussion: Turn[];
  reply: Reply | null;
  stale: boolean;
}

export interface Verification {
  status: "checked" | "skipped" | "off";
  model: string | null;
  checked: number;
  removed: number;
}

export interface ReviewReference {
  ref: string;
  kind: "canon" | "research" | "deviation" | "watchlist";
  title: string;
}

export interface SkippedReference {
  ref: string;
  reason: string;
}

export interface ReviewSummary {
  id: string;
  draft: string;
  draft_rev: number;
  state: ReviewState;
  progress: Progress | null;
  error: JobError | null;
  created_at: string;
  updated_at: string;
  checks: Check[];
  dialect: Dialect;
  verify: VerifyMode;
  verification: Verification | null;
  model: string | null;
  generated_at: string | null;
  issue_count?: number;
  open?: number;
}

export interface Review extends ReviewSummary {
  references: ReviewReference[];
  skipped: SkippedReference[];
  outdated: boolean;
  issues: ReviewIssue[] | null;
}

export interface ReviewReferences {
  draft: string;
  draft_rev: number;
  references: ReviewReference[];
  skipped: SkippedReference[];
}

export interface ReviewRequest {
  draft?: string;
  checks?: Check[];
  dialect?: Dialect;
  verify?: VerifyMode;
  include?: string[];
}
