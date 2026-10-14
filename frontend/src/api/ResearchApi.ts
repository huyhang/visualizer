// The one seam between the studio and the server. Components never fetch: they
// reach this through `useApi()`, so tests hand in a fake and the HTTP version
// is a detail of `main.tsx`. Every method is about one world, bound when the
// implementation is made.

import type {
  Accepted,
  ArticleRef,
  AskRequest,
  Availability,
  DocumentResult,
  Draft,
  InboxRow,
  Job,
  Media,
  NoteRequest,
  NoteSaved,
  NoteSummary,
  Query,
  RefineRequest,
} from "./types";

export interface ResearchApi {
  readonly world: string;

  availability(): Promise<Availability>;

  /** Recent jobs, newest first. Reading the list never asks the box. */
  listJobs(limit?: number): Promise<Job[]>;
  /** One job, as the box now reports it; importing its result once it is done. */
  getJob(id: string): Promise<Job>;
  ask(request: AskRequest): Promise<Job>;
  approvePlan(id: string, queries: Query[]): Promise<Job>;
  cancel(id: string): Promise<Job>;

  inbox(): Promise<InboxRow[]>;
  draft(slug: string): Promise<Draft>;
  refine(slug: string, request: RefineRequest): Promise<Job>;
  /** Keep a whole draft, as it stands, as a research note. */
  acceptDraft(slug: string): Promise<Accepted>;
  /** Close a draft the writer has finished with. */
  closeDraft(slug: string): Promise<void>;
  /** Turn a draft down. */
  discardDraft(slug: string): Promise<void>;
  imagePreviewUrl(slug: string, index: number): string;
  importImage(slug: string, index: number): Promise<Media>;

  listNotes(): Promise<NoteSummary[]>;
  getNote(slug: string): Promise<DocumentResult>;
  saveNote(request: NoteRequest): Promise<NoteSaved>;

  /** Where an article is read in Akasha's own editor. */
  articleUrl(ref: ArticleRef): string;
}
