// The open draft and the listing it belongs to, kept in step. The draft and its
// row are two reads of one record; every change to one is a named transition
// that changes both, so a rename can never show the old name in the picker.

import type { Draft, DraftRow } from "../api/types";

export interface DraftState {
  rows: DraftRow[];
  current: Draft;
  sectionRev: number;
}

const withRow = (rows: DraftRow[], id: string, patch: Partial<DraftRow>) =>
  rows.map((row) => (row.id === id ? { ...row, ...patch } : row));

/** A save came back: adopt it, and carry it into its row. */
export function saved(state: DraftState, record: Draft): DraftState {
  const row = {
    name: record.name,
    primary: record.primary,
    rev: record.rev,
    word_count: record.word_count,
  };
  return {
    rows: withRow(state.rows, record.id, row),
    current: { ...state.current, ...record },
    sectionRev: record.section_rev ?? state.sectionRev,
  };
}

/** A write that moved the section itself, not the draft. */
export function sectionChanged(state: DraftState, revision: number): DraftState {
  return { ...state, sectionRev: revision };
}

export function renamed(state: DraftState, name: string): DraftState {
  return {
    ...state,
    rows: withRow(state.rows, state.current.id, { name }),
    current: { ...state.current, name },
  };
}

/** The open draft is now the one readers, search and exports see. */
export function promoted(state: DraftState, revision: number): DraftState {
  return {
    rows: state.rows.map((row) => ({ ...row, primary: row.id === state.current.id })),
    current: { ...state.current, primary: true },
    sectionRev: revision,
  };
}

/** The draft picker's choices, in listing order. */
export function draftOptions(state: DraftState) {
  return state.rows.map((row) => ({
    value: row.id,
    label: `${row.name}${row.primary ? " (Primary)" : ""}`,
    current: row.id === state.current.id,
  }));
}

/** Which draft actions can change anything right now; the rest are not shown. */
export function draftCapabilities(count: number, currentIsPrimary: boolean) {
  return {
    canSwitch: count > 1,
    canCompare: count > 1,
    canPromote: count > 1 && !currentIsPrimary,
    showPrimaryBadge: count > 1 && currentIsPrimary,
  };
}

/** The draft a page asked for, else the primary, else the first. */
export function chooseDraft(
  rows: DraftRow[],
  requested: string | null,
): DraftRow | undefined {
  return (
    rows.find((row) => row.id === requested) ?? rows.find((row) => row.primary) ?? rows[0]
  );
}
