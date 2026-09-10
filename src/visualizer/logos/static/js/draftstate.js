// The workspace's mutable draft state, with its transitions named.
//
// The open draft and its row in the listing are two separate reads of the same
// record, and keeping them in step used to be a scatter of find-and-assign at
// each call site. Forgetting one is exactly how a rename came to show the old
// name in the selector until autosave caught up. Owning both here makes every
// transition a named operation that a test can drive without a browser.

export function createDraftState({ drafts, current, sectionRev }) {
  const rows = [...drafts];
  let open = current;
  let rev = sectionRev;

  const rowFor = (id) => rows.find((item) => item.id === id);

  return {
    get current() { return open; },
    get rows() { return rows; },
    get count() { return rows.length; },
    get sectionRev() { return rev; },

    /** A draft save came back: adopt it, and carry it into the listing row. */
    saved(record) {
      open = record;
      if (record.section_rev !== undefined) rev = record.section_rev;
      const row = rowFor(record.id);
      if (row) Object.assign(row, record);
    },

    /** A write that moved the section itself, not the draft. */
    sectionChanged(revision) {
      rev = revision;
    },

    renamed(name) {
      open.name = name;
      const row = rowFor(open.id);
      if (row) row.name = name;
    },

    /** The open draft is now the one readers, search and exports see. */
    promoted(revision) {
      rev = revision;
      for (const item of rows) item.primary = item.id === open.id;
      open.primary = true;
    },

    /** What the draft selector should show, in listing order. */
    options() {
      return rows.map((item) => ({
        value: item.id,
        text: `${item.name}${item.primary ? " (Primary)" : ""}`,
        current: item.id === open.id,
      }));
    },
  };
}
