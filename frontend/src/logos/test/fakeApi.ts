// An in-memory LogosApi for tests: one book, one section, its drafts, the
// Coach and LLM reviews, each call recorded. Reviews finish on the first poll
// unless a test holds them, the way the fake GPU box walks its stages.

import { vi } from "vitest";
import type { LogosApi, SectionAddress } from "../api/LogosApi";
import { LogosApiError } from "../api/errors";
import type {
  Availability,
  CoachIssue,
  Draft,
  DraftRow,
  Entity,
  Manuscript,
  Review,
  ReviewIssue,
  Section,
} from "../api/types";
import type { LogosDocument } from "../doc/types";
import { doc, para, text } from "./docs";

export const AT: SectionAddress = { book: "ember", volume: "one", section: "gate" };

export const CHAPTER: LogosDocument = doc(
  para("p1", text("Lin lifted the teapot and poured.")),
  para("p2", text("The gate was very very old.")),
);

export function reviewIssue(id: string, patch: Partial<ReviewIssue> = {}): ReviewIssue {
  return {
    id,
    check: "anachronism",
    severity: "warning",
    confidence: "likely",
    block: "p1",
    quote: "lifted the teapot",
    message: "Song tea was whisked in bowls.",
    suggestion: "Show her whisking tea.",
    replacement: "whisked the tea",
    reference: "ember/research/tea",
    verified: true,
    status: "open",
    dismissed_before: null,
    discussion: [],
    reply: null,
    stale: false,
    ...patch,
  };
}

export interface FakeState {
  manuscript: Manuscript;
  section: Section;
  drafts: Draft[];
  sectionRev: number;
  coach: CoachIssue[];
  entities: Entity[];
  availability: Availability;
  reviews: Review[];
  /** Issues the next review comes back with. */
  nextIssues: ReviewIssue[];
  /** Hold reviews in "running" until a test lets them finish. */
  holdReviews: boolean;
  failSaves: number | null;
}

export function fakeState(patch: Partial<FakeState> = {}): FakeState {
  const draft: Draft = {
    id: "draft-1",
    name: "Draft 1",
    primary: true,
    rev: 3,
    document: CHAPTER,
  };
  return {
    manuscript: {
      book: AT.book,
      title: "The Ember Pact",
      world: "ember",
      rev: 1,
      permissions: { read: true, write: true },
      volumes: [
        {
          id: AT.volume,
          number: 1,
          title: "Volume One",
          sections: [
            {
              id: AT.section,
              volume: AT.volume,
              kind: "chapter",
              number: 1,
              title: "The Gate",
              primary_draft_id: "draft-1",
              rev: 5,
            },
            {
              id: "tea",
              volume: AT.volume,
              kind: "chapter",
              number: 2,
              title: "Tea",
              primary_draft_id: "draft-1",
              rev: 1,
            },
          ],
        },
      ],
    },
    section: {
      id: AT.section,
      volume: AT.volume,
      kind: "chapter",
      number: 1,
      title: "The Gate",
      primary_draft_id: "draft-1",
      rev: 5,
      document: CHAPTER,
    },
    drafts: [draft],
    sectionRev: 5,
    coach: [],
    entities: [],
    availability: {
      state: "ready",
      can_submit: true,
      message: "Ready.",
      model: "qwen3:30b",
      verifier: "up",
      private: true,
    },
    reviews: [],
    nextIssues: [
      reviewIssue("i1"),
      reviewIssue("i2", {
        check: "prose",
        severity: "info",
        block: "p2",
        quote: "very very",
        replacement: null,
        reference: null,
      }),
    ],
    holdReviews: false,
    failSaves: null,
    ...patch,
  };
}

const row = ({ document: _d, ...rest }: Draft): DraftRow => rest;

export function fakeApi(state: FakeState = fakeState()) {
  const findReview = (id: string) => {
    const found = state.reviews.find((review) => review.id === id);
    if (!found) throw new LogosApiError(404, "No such review.");
    return found;
  };
  const findIssue = (reviewId: string, issueId: string) => {
    const issue = findReview(reviewId).issues?.find((i) => i.id === issueId);
    if (!issue) throw new LogosApiError(404, "No such issue.");
    return issue;
  };
  const replace = (reviewId: string, issue: ReviewIssue) => {
    const review = findReview(reviewId);
    review.issues = (review.issues ?? []).map((i) => (i.id === issue.id ? issue : i));
    return issue;
  };

  const api: LogosApi = {
    manuscript: vi.fn(async () => structuredClone(state.manuscript)),
    section: vi.fn(async () => structuredClone(state.section)),
    createSection: vi.fn(async (_b, volume, id, body) => ({
      ...state.manuscript.volumes[0]!.sections[0]!,
      id,
      volume,
      kind: body.kind,
      title: body.title,
    })),
    updateSectionTitle: vi.fn(async (_at, title, revision) => {
      if (revision !== state.sectionRev) throw new LogosApiError(409, "Stale.");
      state.sectionRev += 1;
      state.section = { ...state.section, title, rev: state.sectionRev };
      return state.section;
    }),
    drafts: vi.fn(async () => ({
      drafts: state.drafts.map(row),
      section_rev: state.sectionRev,
    })),
    draft: vi.fn(async (_at, id) => {
      const found = state.drafts.find((d) => d.id === id);
      if (!found) throw new LogosApiError(404, "No such draft.");
      return structuredClone(found);
    }),
    createDraft: vi.fn(async (_at, name, source) => {
      const from = state.drafts.find((d) => d.id === source)!;
      const created: Draft = {
        ...from,
        id: `draft-${state.drafts.length + 1}`,
        name,
        primary: false,
        rev: 1,
      };
      state.drafts.push(created);
      return structuredClone(created);
    }),
    saveDraft: vi.fn(async (_at, id, body, revision) => {
      if (state.failSaves !== null) throw new LogosApiError(state.failSaves, "Refused.");
      const at = state.drafts.findIndex((d) => d.id === id);
      const held = state.drafts[at]!;
      if (revision !== held.rev) throw new LogosApiError(409, "Someone saved first.");
      const saved = { ...held, ...body, rev: held.rev + 1 };
      state.drafts[at] = saved;
      return structuredClone(saved);
    }),
    makePrimary: vi.fn(async (_at, id) => {
      state.drafts = state.drafts.map((d) => ({ ...d, primary: d.id === id }));
      state.sectionRev += 1;
      return { section_rev: state.sectionRev };
    }),
    entities: vi.fn(async () => structuredClone(state.entities)),
    coach: vi.fn(async (_b, _document, dialect) => ({
      dialect,
      issues: structuredClone(state.coach),
    })),
    reviewAvailability: vi.fn(async () => structuredClone(state.availability)),
    reviewReferences: vi.fn(async (_at, draft) => ({
      draft,
      draft_rev: 3,
      references: [
        { ref: "ember/research/tea", kind: "research" as const, title: "Song tea" },
      ],
      skipped: [{ ref: "ember/research-inbox/rumour", reason: "unreviewed_research" }],
    })),
    askForReview: vi.fn(async (_at, request) => {
      const review: Review = {
        id: `r${state.reviews.length + 1}`,
        draft: request.draft ?? "draft-1",
        draft_rev: 3,
        state: "running",
        progress: { stage: "reviewing" },
        error: null,
        created_at: "2026-10-14T10:00:00Z",
        updated_at: "2026-10-14T10:00:00Z",
        checks: request.checks ?? ["continuity", "anachronism", "prose"],
        dialect: request.dialect ?? "en-US",
        verify: request.verify ?? "auto",
        verification: null,
        model: null,
        generated_at: null,
        references: [{ ref: "ember/research/tea", kind: "research", title: "Song tea" }],
        skipped: [],
        outdated: false,
        issues: null,
      };
      state.reviews.unshift(review);
      return structuredClone(review);
    }),
    reviews: vi.fn(async () =>
      state.reviews.map((review) => ({
        ...review,
        issue_count: review.issues?.length ?? 0,
        open: review.issues?.filter((i) => i.status === "open").length ?? 0,
      })),
    ),
    review: vi.fn(async (_at, id) => {
      const review = findReview(id);
      if (review.state === "running" && !state.holdReviews) {
        Object.assign(review, {
          state: "done",
          progress: null,
          issues: structuredClone(state.nextIssues),
          verification: { status: "checked", model: "gemma3", checked: 2, removed: 0 },
        });
      }
      return structuredClone(review);
    }),
    cancelReview: vi.fn(async (_at, id) => {
      const review = findReview(id);
      review.state = "cancelled";
      return structuredClone(review);
    }),
    setIssueStatus: vi.fn(async (_at, reviewId, issueId, status) =>
      structuredClone(
        replace(reviewId, {
          ...findIssue(reviewId, issueId),
          status,
          dismissed_before: null,
        }),
      ),
    ),
    issue: vi.fn(async (_at, reviewId, issueId) => {
      const issue = findIssue(reviewId, issueId);
      if (issue.reply?.state === "running") {
        return structuredClone(
          replace(reviewId, {
            ...issue,
            reply: null,
            discussion: [
              ...issue.discussion,
              {
                role: "editor",
                text: "A kettle is right.",
                at: null,
                stance: "revises",
                suggestion: "Say kettle.",
                replacement: "lifted the kettle",
                model: "qwen3:30b",
              },
            ],
          }),
        );
      }
      return structuredClone(issue);
    }),
    discuss: vi.fn(async (_at, reviewId, issueId, message) => {
      const issue = findIssue(reviewId, issueId);
      return structuredClone(
        replace(reviewId, {
          ...issue,
          discussion: [
            ...issue.discussion,
            {
              role: "writer",
              text: message,
              at: null,
              stance: null,
              suggestion: null,
              replacement: null,
              model: null,
            },
          ],
          reply: { state: "running", progress: { stage: "replying" }, error: null },
        }),
      );
    }),
    articleUrl: ({ database, collection, id }) =>
      `/akasha/#/${database}/${collection}/${id}`,
    readerUrl: (at, block = null, draft = null) =>
      `/read/${at.volume}/${at.section}${block ? `#${block}` : ""}${draft ? `?draft=${draft}` : ""}`,
    contentsUrl: (book) => `/contents/${book}`,
    writerUrl: (at, draft = null) =>
      `/write/${at.volume}/${at.section}${draft ? `?draft=${draft}` : ""}`,
  };
  return { api, state };
}
