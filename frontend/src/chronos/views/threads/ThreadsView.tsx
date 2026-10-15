// A book's threads: filtered, paged, ordered by name. The filtering, ordering
// and paging happen on the server; this drives it and draws the rows.
//
// The last filter and page are remembered per book for the session, so coming
// back from a thread lands on the same view the writer left.

import { useState } from "react";
import type { PlotlineRow } from "../../api/types";
import { usePlotlines } from "../../hooks/queries";
import { useSessionMemory } from "../../hooks/useSessionMemory";
import { useThreads, type ThreadInfo } from "../../hooks/useThreads";
import { to } from "../../logic/route";
import { plural } from "../../logic/text";
import { GoalChip, ProblemCount, ThreadDot } from "../../components/common/Chips";
import { SearchField, useDebounced } from "../../components/common/Fields";
import { Link } from "../../components/common/Link";
import { Page, PageHeader } from "../../components/common/Page";
import { Pager } from "../../components/common/Pager";
import { QueryState } from "../../components/common/QueryState";
import { useActions } from "../../components/shell/Actions";
import { useBookScope } from "../../components/shell/BookScope";
import { useInspector } from "../../components/shell/InspectorContext";
import { Button, IconButton } from "../../../components/ui/Button";
import { EmptyState } from "../../../components/ui/EmptyState";

const PER_PAGE = 20;

/**
 * The filter being typed and the page being read, starting from where this
 * book was left. A new filter starts again at its first page.
 */
function usePaging(book: string) {
  const [paged, setPaged] = useSessionMemory(`threads:${book}`, { filter: "", page: 1 });
  const [typed, setTyped] = useState(paged.filter);
  const filter = useDebounced(typed.trim());
  const page = paged.filter === filter ? paged.page : 1;
  return {
    typed,
    setTyped: (text: string) => {
      setTyped(text);
      setPaged({ filter: text.trim(), page: 1 });
    },
    filter,
    page,
    setPage: (p: number) => setPaged({ filter, page: p }),
  };
}

function ThreadRow({ row, thread }: { row: PlotlineRow; thread?: ThreadInfo }) {
  const { id: book } = useBookScope();
  const inspector = useInspector();
  return (
    <li className="cw-thread-row">
      <Link className="cw-thread-row-main" to={to.plotline(book, row.id)}>
        <ThreadDot thread={thread} size={12} />
        <span className="cw-thread-row-text">
          <span className="cw-thread-row-name">{row.name}</span>
          {row.overview ? (
            <span className="cw-thread-row-overview">{row.overview}</span>
          ) : null}
        </span>
      </Link>
      <div className="cw-thread-row-goals">
        {row.goals.map((g) => (
          <GoalChip
            key={g.id}
            goal={g}
            onOpen={(id) => inspector.open({ kind: "goal", id })}
          />
        ))}
      </div>
      <div className="cw-thread-row-health">
        <ProblemCount count={row.conflicts} />
      </div>
      <IconButton
        icon="panel"
        label="Glance at this thread"
        onClick={() => inspector.open({ kind: "thread", id: row.id })}
      />
    </li>
  );
}

export function ThreadsView() {
  const { id: book, book: record, calendar, canWrite } = useBookScope();
  const { get } = useThreads(book);
  const { newThread, editBook } = useActions();
  const { typed, setTyped, filter, page, setPage } = usePaging(book);
  const query = usePlotlines(book, { filter, page, perPage: PER_PAGE, calendar });

  return (
    <Page label="Threads">
      <PageHeader
        eyebrow="Threads"
        title={record?.title || book}
        subtitle={record?.overview || undefined}
        actions={
          <>
            {canWrite && editBook ? (
              <Button icon="settings" onClick={editBook}>
                Book settings
              </Button>
            ) : null}
            {canWrite && newThread ? (
              <Button variant="primary" icon="plus" onClick={newThread}>
                New thread
              </Button>
            ) : null}
          </>
        }
      >
        <SearchField
          value={typed}
          onChange={setTyped}
          placeholder="Filter threads…"
          label="Filter threads"
        />
      </PageHeader>
      <QueryState query={query}>
        {(data) =>
          data.plotlines.length ? (
            <>
              <div className="cw-list-head" aria-hidden="true">
                <span>Thread</span>
                <span>Goals</span>
                <span>Health</span>
                <span />
              </div>
              <ul className="cw-thread-list">
                {data.plotlines.map((row) => (
                  <ThreadRow key={row.id} row={row} thread={get(row.id)} />
                ))}
              </ul>
              <Pager
                page={data.page}
                pages={data.pages}
                total={plural(data.total, "thread")}
                onPage={setPage}
              />
            </>
          ) : (
            <EmptyState
              icon="branch"
              title={filter ? "No thread matches" : "No threads yet"}
            >
              {filter
                ? `Nothing here contains every word of “${filter}”.`
                : "A thread is one line of the story, scene by scene, toward the book's ending."}
            </EmptyState>
          )
        }
      </QueryState>
    </Page>
  );
}
