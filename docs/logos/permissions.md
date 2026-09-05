# Logos permissions

Logos keeps no access-control records of its own. Every manuscript, volume and
section inherits access from its Chronos book.

## One book, one grant

A Chronos book grant lives in the shared `_auth` database with the resource type
`book` and the book id as its scope. Both services evaluate that same row:

```text
Chronos book: wheel-of-time
└── Logos manuscript
    ├── every volume
    └── every section, and its retained revisions
```

There are no volume-level or section-level grants. Creating Logos content does
not create or copy a grant, and deploying Logos requires no permission migration
for books that already exist — the grant that already governs the timeline
governs the manuscript from the moment the service is mounted.

This is deliberately separate from the other two resource kinds: a grant on the
Akasha *world* `ember` confers nothing on the *book* `ember`, and neither confers
anything on a reusable Chronos calendar.

## Roles

| Chronos book role | Permissions | What it can do in Logos |
| --- | --- | --- |
| Reader | `read` | Read, search and export the manuscript; manage only their own private notes, checklists, bookmarks and reading position |
| Editor | `read`, `write` | The above, plus create, update, reorder and restore manuscript content and edit publication metadata |
| Owner | `read`, `write`, `delete` | The above, plus delete sections, volumes and the manuscript, and manage sharing |

Administrators are not exempt. An administrator holding no grant on a book cannot
read its Chronos content or its prose; the admin role governs accounts and access
management, not the content itself.

## By operation

- `GET` requires `read`.
- Private reader-item and position writes require `read`; they address only the
  signed-in account and cannot alter another account or the manuscript.
- Creating, updating, reordering and restoring require `write`.
- Deleting a section, volume or manuscript requires `delete`.

**The grant is checked before anything is loaded.** A caller without one gets
`403 FORBIDDEN` whether or not the book exists, so the API is not an oracle for
which books are on the shelf. A caller who does hold a grant gets
`404 BOOK_NOT_FOUND` when the Chronos book itself is missing.

## Sharing and revocation

Sharing a Chronos book immediately grants the same role over its whole
manuscript; revoking it immediately removes that access. There is no
synchronisation job and no window in which the two services disagree, because
there is only one row and both read it.

Sharing is managed through the existing Chronos collaborator API and the shared
account page. Logos deliberately exposes no collaborator endpoints of its own.

Note the existing cascade: sharing a book may also grant the recipient read
access to the book's Akasha world, when the owner is entitled to share it, so
that referenced characters and places can be read. It never grants Akasha write
access, and a world grant alone confers nothing on Chronos or Logos.

## Where permission ends and reference begins

Permissions answer *who may attempt* a deletion. Whether it is currently safe is
a separate question, answered by what still references what:

- Chronos refuses to delete a book while a manuscript exists for it
  (`409 MANUSCRIPT_IN_USE`). The owner deletes the manuscript first, and that
  operation permanently removes its retained revisions.
- Chronos refuses to delete an event a live section is written from
  (`409 EVENT_IN_MANUSCRIPT`), and `detach=true` does not override it.
- An event named only by an *older, retained* revision does not block anything.
  History is not a live reference. Restoring that revision later is what
  revalidates it — and fails then if the event has really gone.
- Deleting a non-empty manuscript or volume requires `cascade=true`.

These checks protect prose without giving Logos any ownership of Chronos data.
