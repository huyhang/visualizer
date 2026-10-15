// Everything the writing page asks of Logos. Components and hooks receive this
// through `ApiProvider`; the page builds the HTTP one, tests build a fake.

import type { ArticleRef, LogosDocument } from "../doc/types";
import type {
  Availability,
  CoachReview,
  Dialect,
  Draft,
  DraftListing,
  Entity,
  IssueStatus,
  Manuscript,
  Review,
  ReviewIssue,
  ReviewReferences,
  ReviewRequest,
  ReviewSummary,
  Section,
  SectionKind,
  SectionSummary,
} from "./types";

/** Where a section is: the address every section-level call takes. */
export interface SectionAddress {
  book: string;
  volume: string;
  section: string;
}

export interface NewSection {
  kind: SectionKind;
  title: string;
}

export interface LogosApi {
  manuscript(book: string): Promise<Manuscript>;
  section(at: SectionAddress): Promise<Section>;
  createSection(
    book: string,
    volume: string,
    section: string,
    body: NewSection,
  ): Promise<SectionSummary>;
  updateSectionTitle(
    at: SectionAddress,
    title: string | null,
    revision: number,
  ): Promise<SectionSummary>;

  drafts(at: SectionAddress): Promise<DraftListing>;
  draft(at: SectionAddress, draft: string): Promise<Draft>;
  createDraft(at: SectionAddress, name: string, source: string): Promise<Draft>;
  saveDraft(
    at: SectionAddress,
    draft: string,
    body: { name: string; document: LogosDocument },
    revision: number,
    keepalive?: boolean,
  ): Promise<Draft>;
  makePrimary(
    at: SectionAddress,
    draft: string,
    sectionRevision: number,
  ): Promise<{ section_rev: number }>;

  entities(book: string, query: string): Promise<Entity[]>;
  coach(book: string, document: LogosDocument, dialect: Dialect): Promise<CoachReview>;

  reviewAvailability(): Promise<Availability>;
  reviewReferences(
    at: SectionAddress,
    draft: string,
    include: string[],
  ): Promise<ReviewReferences>;
  askForReview(at: SectionAddress, request: ReviewRequest): Promise<Review>;
  reviews(at: SectionAddress): Promise<ReviewSummary[]>;
  review(at: SectionAddress, id: string): Promise<Review>;
  cancelReview(at: SectionAddress, id: string): Promise<Review>;
  setIssueStatus(
    at: SectionAddress,
    review: string,
    issue: string,
    status: IssueStatus,
  ): Promise<ReviewIssue>;
  issue(at: SectionAddress, review: string, issue: string): Promise<ReviewIssue>;
  discuss(
    at: SectionAddress,
    review: string,
    issue: string,
    text: string,
  ): Promise<ReviewIssue>;

  /** Where an Akasha article opens, for links out of the page. */
  articleUrl(ref: ArticleRef): string;
  /** The reader, the contents page and this page, for navigation. */
  readerUrl(at: SectionAddress, block?: string | null, draft?: string | null): string;
  contentsUrl(book: string): string;
  writerUrl(at: SectionAddress, draft?: string | null): string;
}
