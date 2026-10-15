// Previous / next under a paged list, with where you are in it.

import { Button } from "../../../components/ui/Button";

export function Pager({
  page,
  pages,
  total,
  onPage,
}: {
  page: number;
  pages: number;
  /** "5 threads": what the whole list holds. */
  total: string;
  onPage: (page: number) => void;
}) {
  return (
    <nav className="cw-pager" aria-label="Pages">
      <Button
        size="sm"
        variant="ghost"
        icon="arrowLeft"
        disabled={page <= 1}
        onClick={() => onPage(page - 1)}
      >
        Previous
      </Button>
      <span className="cw-pager-where">
        Page {page} of {Math.max(pages, 1)} · {total}
      </span>
      <Button
        size="sm"
        variant="ghost"
        disabled={page >= pages}
        onClick={() => onPage(page + 1)}
      >
        Next
      </Button>
    </nav>
  );
}
