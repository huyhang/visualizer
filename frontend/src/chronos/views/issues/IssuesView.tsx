// The book's report: everything wrong across all of its threads, one issue
// per problem however many threads can see it -- and triage, for working down
// it one issue at a time with each one open beside the list.

import { useCallback, useEffect, useRef, useState } from "react";
import type { BookReport, Issue, IssueGroup } from "../../api/types";
import { useReport } from "../../hooks/queries";
import { useRoute } from "../../hooks/useRoute";
import { useThreads } from "../../hooks/useThreads";
import { useDeps } from "../../deps";
import {
  narrow,
  readingOrder,
  rollup,
  verdict,
  homeThread,
  issueKey,
} from "../../logic/report";
import { to } from "../../logic/route";
import { plural } from "../../logic/text";
import { ArticleChip, Chip, ThreadChip, ThreadDot } from "../../components/common/Chips";
import { FindingText } from "../../components/common/FindingText";
import { Page, PageHeader } from "../../components/common/Page";
import { QueryState } from "../../components/common/QueryState";
import { useBookScope } from "../../components/shell/BookScope";
import { useInspector } from "../../components/shell/InspectorContext";
import { Button } from "../../../components/ui/Button";
import { Icon } from "../../../components/ui/Icon";
import { useTriage, type Triage } from "./useTriage";

export const NOTES_KEY = "chronos.report.notes";

function useNotesOpen(): [boolean, (open: boolean) => void] {
  const { store } = useDeps();
  const [open, setOpen] = useState(() => store.get(NOTES_KEY) !== "closed");
  const remember = (next: boolean) => {
    store.set(NOTES_KEY, next ? "open" : "closed");
    setOpen(next);
  };
  return [open, remember];
}

function VerdictLine({
  problems,
  undated,
  narrowed,
}: {
  problems: number;
  undated: number;
  narrowed: boolean;
}) {
  if (!problems && !undated) {
    return (
      <p className="cw-verdict is-sound">
        <Icon name="check" size={18} />
        {narrowed
          ? "Nothing to fix on this thread."
          : "Nothing to fix — this book holds together."}
      </p>
    );
  }
  return (
    <p className="cw-verdict">
      {problems ? (
        <span className="cw-tally is-conflict">
          <strong>{problems}</strong> {problems === 1 ? "problem" : "problems"}
        </span>
      ) : null}
      {problems && undated ? (
        <span className="cw-tally-sep" aria-hidden="true">
          ·
        </span>
      ) : null}
      {undated ? (
        <span className="cw-tally">
          <strong>{undated}</strong> {undated === 1 ? "scene" : "scenes"} still waiting for
          a time
        </span>
      ) : null}
    </p>
  );
}

function IssueRow({
  issue,
  selected,
  onSelect,
}: {
  issue: Issue;
  selected: boolean;
  onSelect: () => void;
}) {
  const { id: book } = useBookScope();
  const { get } = useThreads(book);
  const inspector = useInspector();
  const { go } = useRoute();
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (selected) ref.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [selected]);
  const sceneId = issue.scene?.id ?? null;
  return (
    <div
      ref={ref}
      className={`cw-issue${selected ? " is-selected" : ""}`}
      aria-current={selected || undefined}
    >
      <button
        type="button"
        className="cw-issue-select"
        onClick={onSelect}
        aria-label="Look at this issue"
      />
      <div className="cw-issue-head">
        {issue.scene ? (
          <button type="button" className="cw-issue-anchor" onClick={onSelect}>
            {issue.scene.title}
          </button>
        ) : null}
        {issue.goal ? (
          <button type="button" className="cw-issue-anchor is-goal" onClick={onSelect}>
            <Icon name="target" size={14} /> {issue.goal.title}
          </button>
        ) : null}
        {issue.plotlines.map((p) => (
          <ThreadChip
            key={p.id}
            id={p.id}
            thread={get(p.id)}
            onOpen={(id) => go(to.plotline(book, id, sceneId))}
          />
        ))}
      </div>
      <p className="cw-issue-text">
        <FindingText book={book} message={issue.message} refs={issue.refs} />
      </p>
      {issue.events.length || issue.goals.length || issue.refs.length ? (
        <div className="cw-chip-row">
          {issue.events.map((e) => (
            <Chip
              key={e.id}
              icon="scenes"
              onClick={() => inspector.open({ kind: "scene", id: e.id })}
            >
              {e.title}
            </Chip>
          ))}
          {issue.goals.map((g) => (
            <Chip
              key={g.id}
              icon="target"
              onClick={() => inspector.open({ kind: "goal", id: g.id })}
            >
              {g.title}
            </Chip>
          ))}
          {issue.refs.map((r) => (
            <ArticleChip
              key={`${r.collection}/${r.id}`}
              book={book}
              entity={r}
              onOpen={(entity) => inspector.open({ kind: "article", ref: entity })}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}

function GroupCard({
  group,
  triage,
  order,
}: {
  group: IssueGroup;
  triage: Triage;
  order: Issue[];
}) {
  return (
    <section className={`cw-issue-group is-${group.severity}`}>
      <h3 className="cw-issue-group-title">
        <span>{group.title}</span>
        <span className="cw-issue-count">{group.issues.length}</span>
      </h3>
      <div className="cw-issue-list">
        {group.issues.map((issue) => {
          const n = order.indexOf(issue);
          return (
            <IssueRow
              key={issueKey(issue)}
              issue={issue}
              selected={triage.on && n === triage.index}
              onSelect={() => triage.choose(n)}
            />
          );
        })}
      </div>
    </section>
  );
}

function Rollup({
  report,
  thread,
  onThread,
}: {
  report: BookReport;
  thread: string;
  onThread: (id: string) => void;
}) {
  const { id: book } = useBookScope();
  const { get } = useThreads(book);
  if (report.plotlines.length < 2) return null;
  return (
    <section className="cw-rollup">
      <h2 className="cw-section-title">By thread</h2>
      <p className="cw-muted cw-small">
        {thread
          ? "Showing one thread — choose it again for all of them."
          : "Most problems first. Choose a thread to narrow the report to it."}
      </p>
      <ul className="cw-rollup-list">
        {rollup(report).map((p) => (
          <li key={p.id}>
            <button
              type="button"
              className={`cw-rollup-row${p.id === thread ? " is-current" : ""}`}
              aria-pressed={p.id === thread}
              onClick={() => onThread(p.id === thread ? "" : p.id)}
            >
              <ThreadDot thread={get(p.id)} />
              <span className="cw-rollup-name">{p.title ?? p.id}</span>
              <span className={p.problems ? "cw-problems" : "cw-quiet"}>
                {p.problems || "—"}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Report({ report }: { report: BookReport }) {
  const inspector = useInspector();
  const [thread, setThread] = useState("");
  const [notesOpen, setNotesOpen] = useNotesOpen();
  const problems = narrow(report.problems, thread);
  const notes = narrow(report.notes, thread);
  const order = readingOrder(problems, notes, notesOpen);
  const openIssue = useCallback(
    (issue: Issue) => {
      if (issue.scene) inspector.open({ kind: "scene", id: issue.scene.id });
      else if (issue.goal) inspector.open({ kind: "goal", id: issue.goal.id });
      else if (homeThread(issue))
        inspector.open({ kind: "thread", id: homeThread(issue) ?? "" });
    },
    [inspector],
  );
  const triage = useTriage(order, openIssue);
  const tally = verdict(problems, notes);
  const noteCount = notes.reduce((n, g) => n + g.issues.length, 0);

  return (
    <>
      <div className="cw-report-bar">
        <VerdictLine
          problems={tally.problems}
          undated={tally.undated}
          narrowed={Boolean(thread)}
        />
        {order.length ? (
          triage.on ? (
            <div className="cw-triage-bar" role="group" aria-label="Triage">
              <span className="cw-triage-where">
                {triage.index + 1} of {order.length}
              </span>
              <Button
                size="sm"
                variant="ghost"
                icon="arrowUp"
                onClick={() => triage.move(-1)}
                disabled={triage.index <= 0}
              >
                Previous
              </Button>
              <Button
                size="sm"
                variant="ghost"
                icon="arrowDown"
                onClick={() => triage.move(1)}
                disabled={triage.index >= order.length - 1}
              >
                Next
              </Button>
              <Button size="sm" onClick={triage.stop}>
                Done
              </Button>
            </div>
          ) : (
            <Button variant="primary" icon="flag" onClick={triage.start}>
              Triage {plural(order.length, "issue")}
            </Button>
          )
        ) : null}
      </div>
      {triage.on ? (
        <p className="cw-muted cw-small cw-triage-hint">
          <kbd className="cw-kbd">J</kbd> / <kbd className="cw-kbd">K</kbd> move through the
          list. Each issue opens beside it, and the list re-checks as soon as a fix is
          saved.
        </p>
      ) : null}
      {problems.map((g) => (
        <GroupCard key={g.title} group={g} triage={triage} order={order} />
      ))}
      {notes.length ? (
        <>
          <div className="cw-section-row">
            <h2 className="cw-section-title">Worth knowing</h2>
            <Button size="sm" variant="ghost" onClick={() => setNotesOpen(!notesOpen)}>
              {notesOpen ? "Hide" : `Show ${plural(noteCount, "note")}`}
            </Button>
          </div>
          {notesOpen
            ? notes.map((g) => (
                <GroupCard key={g.title} group={g} triage={triage} order={order} />
              ))
            : null}
        </>
      ) : null}
      <Rollup report={report} thread={thread} onThread={setThread} />
    </>
  );
}

export function IssuesView() {
  const { id: book, book: record, calendar } = useBookScope();
  const query = useReport(book, calendar);
  return (
    <Page label="Issues">
      <PageHeader
        eyebrow={record?.title || book}
        title="Issues"
        subtitle="Everything the story rules can see across this book's threads. A problem is listed once, however many threads it shows up on."
      />
      <QueryState query={query}>{(report) => <Report report={report} />}</QueryState>
    </Page>
  );
}
