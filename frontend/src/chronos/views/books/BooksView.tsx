// The shelf: every book you can read, and the way to start another.
// Plotlines are scoped to a book, so this is where a session begins.

import type { Book } from "../../api/types";
import { useBooks } from "../../hooks/queries";
import { to } from "../../logic/route";
import { plural } from "../../logic/text";
import { Link } from "../../components/common/Link";
import { Page, PageHeader } from "../../components/common/Page";
import { QueryState } from "../../components/common/QueryState";
import { useActions } from "../../components/shell/Actions";
import { Badge } from "../../../components/ui/Badge";
import { Button } from "../../../components/ui/Button";
import { EmptyState } from "../../../components/ui/EmptyState";
import { Icon } from "../../../components/ui/Icon";

export function sortedBooks(books: Book[]): Book[] {
  return [...books].sort((a, b) => (a.title || a.id).localeCompare(b.title || b.id));
}

function BookCard({ book }: { book: Book }) {
  const conflicted = book.status === "conflicted";
  return (
    <article className="cw-book-card">
      <Link className="cw-book-card-link" to={to.threads(book.id)}>
        <span className="cw-book-card-spine" aria-hidden="true" />
        <span className="cw-book-card-title">{book.title || book.id}</span>
        <span className="cw-book-card-id">{book.id}</span>
        {book.overview ? (
          <span className="cw-book-card-overview">{book.overview}</span>
        ) : null}
        <span className="cw-book-card-meta">
          <Icon name="branch" size={13} /> {plural(book.plotlines.length, "thread")}
        </span>
      </Link>
      <Link
        className="cw-book-card-status"
        to={conflicted ? to.issues(book.id) : to.threads(book.id)}
        title={
          conflicted ? "See what is wrong with this book" : "Nothing contradicts itself"
        }
      >
        <Badge tone={conflicted ? "danger" : "ok"}>
          {conflicted ? "Conflicted" : "Consistent"}
        </Badge>
      </Link>
    </article>
  );
}

export function BooksView() {
  const query = useBooks();
  const { newBook } = useActions();
  const create = newBook ? (
    <Button variant="primary" icon="plus" onClick={newBook}>
      New book
    </Button>
  ) : null;
  return (
    <Page label="Your books">
      <PageHeader
        eyebrow="Chronos"
        title="Your books"
        subtitle="Choose a book to explore its threads, scenes and goals."
        actions={
          <>
            <Link className="st-btn st-btn-secondary st-btn-md" to={to.calendars()}>
              <Icon name="calendar" /> Calendars
            </Link>
            {create}
          </>
        }
      />
      <QueryState query={query}>
        {(books) =>
          books.length ? (
            <div className="cw-book-grid">
              {sortedBooks(books).map((b) => (
                <BookCard key={b.id} book={b} />
              ))}
            </div>
          ) : (
            <EmptyState icon="book" title="You have no books yet" action={create}>
              A book holds the threads of one story, the scenes they pass through and the
              goals they serve.
            </EmptyState>
          )
        }
      </QueryState>
    </Page>
  );
}
