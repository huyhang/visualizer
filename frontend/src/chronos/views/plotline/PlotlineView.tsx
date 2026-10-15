// One thread: every scene as a card on a vertical timeline, in story order,
// with what the rules say about it marked where the writer will read it.
//
// Arriving at `#/<book>/<thread>/at/<scene>` -- from the report, a finding or
// the inspector -- scrolls to that scene and lights it up, so "here is what is
// wrong" lands on the scene it is wrong about.

import { useEffect, useMemo, useRef } from "react";
import type { EventSummary, GoalRef, Plotline } from "../../api/types";
import { usePlotline } from "../../hooks/queries";
import { useThreads } from "../../hooks/useThreads";
import { eachAlone, placeGoals } from "../../logic/goalPlacing";
import { focusLabel } from "../../logic/plotline/focus";
import { meetCount } from "../../logic/plotline/verdicts";
import { to } from "../../logic/route";
import { allScheduled } from "../../logic/timeaxis";
import { GoalChip, ThreadDot } from "../../components/common/Chips";
import { Link } from "../../components/common/Link";
import { Page, PageHeader } from "../../components/common/Page";
import { QueryState } from "../../components/common/QueryState";
import { UnplacedStrip } from "../../components/common/UnplacedStrip";
import { useActions } from "../../components/shell/Actions";
import { useBookScope } from "../../components/shell/BookScope";
import { useInspector } from "../../components/shell/InspectorContext";
import { Button } from "../../../components/ui/Button";
import { EmptyState } from "../../../components/ui/EmptyState";
import { Icon } from "../../../components/ui/Icon";
import { pathOf } from "../../components/inspector/ThreadPane";
import { ProblemBanner, VerdictNotes } from "./Findings";
import { Timeline } from "./Timeline";
import { useFocusMode } from "./useFocusMode";
import { useJump } from "./useJump";

function Actions({
  plotline,
  events,
  focus: [hidden, toggle],
}: {
  plotline: Plotline;
  events: EventSummary[];
  focus: [boolean, () => void];
}) {
  const { id: book, canWrite } = useBookScope();
  const { editThread } = useActions();
  const meets = meetCount(events);
  const anyFindings = events.some((e) => (e.findings ?? []).length);
  return (
    <>
      {canWrite && editThread ? (
        <Button variant="primary" icon="edit" onClick={() => editThread(plotline.id)}>
          Edit thread
        </Button>
      ) : null}
      {meets ? (
        <Link
          className="st-btn st-btn-secondary st-btn-md"
          to={to.connected(book, plotline.id)}
          title={`Meets ${meets} other thread${meets === 1 ? "" : "s"} along the way`}
        >
          <Icon name="map" /> Connected plots ({meets})
        </Link>
      ) : null}
      {anyFindings ? (
        <Button
          variant="ghost"
          icon="eye"
          aria-pressed={hidden}
          title="Continuity marks stay computed either way — this only hides them."
          onClick={toggle}
        >
          {focusLabel(hidden, plotline.status.conflicts ?? 0)}
        </Button>
      ) : null}
    </>
  );
}

function GoalRow({ goals }: { goals: GoalRef[] }) {
  const inspector = useInspector();
  if (!goals.length) return null;
  return (
    <div className="cw-chip-row">
      {goals.map((g) => (
        <GoalChip
          key={g.id}
          goal={g}
          onOpen={g.missing ? undefined : (id) => inspector.open({ kind: "goal", id })}
        />
      ))}
    </div>
  );
}

function Body({ plotline, focusEvent }: { plotline: Plotline; focusEvent: string | null }) {
  const { id: book } = useBookScope();
  const { get } = useThreads(book);
  const inspector = useInspector();
  const focus = useFocusMode();
  const [hidden] = focus;
  const events = useMemo(() => pathOf(plotline), [plotline]);
  const placed = useMemo(
    () => placeGoals(plotline.goal_refs ?? [], eachAlone(events.map((e) => e.id))),
    [plotline, events],
  );
  const { container, jump } = useJump((id) => inspector.open({ kind: "scene", id }));

  // Arrive once per address. The page re-renders for other reasons -- the
  // inspector opening, focus mode -- and none of them is a reason to scroll
  // back, or to reopen a scene from another thread the writer has closed.
  // Marked done only once the jump has run, so a mount undone before its
  // frame (React's development double mount) still arrives.
  const arrived = useRef<string | null>(null);
  useEffect(() => {
    if (!focusEvent || arrived.current === focusEvent) return;
    const frame = requestAnimationFrame(() => {
      arrived.current = focusEvent;
      jump(focusEvent);
    });
    return () => cancelAnimationFrame(frame);
  }, [focusEvent, jump]);

  return (
    <div ref={container} className={`cw-plotline${hidden ? " is-focus" : ""}`}>
      <PageHeader
        eyebrow={
          <span className="cw-plotline-eyebrow">
            <ThreadDot thread={get(plotline.id)} /> Thread
          </span>
        }
        title={plotline.title || plotline.id}
        subtitle={plotline.overview || undefined}
        actions={<Actions plotline={plotline} events={events} focus={focus} />}
      >
        <GoalRow goals={plotline.goal_refs ?? []} />
        <p className="cw-muted cw-small cw-plotline-note">
          {allScheduled(events)
            ? "Scenes top to bottom in story order — all are scheduled."
            : "Scenes top to bottom in story order — some have no timing yet."}
        </p>
      </PageHeader>
      <UnplacedStrip
        unplaced={placed.unplaced}
        label="Not landed on this thread"
        onGoal={(id) => inspector.open({ kind: "goal", id })}
      />
      <div className="cw-plotline-marks">
        <ProblemBanner events={events} status={plotline.status} onJump={jump} />
        <VerdictNotes status={plotline.status} events={events} />
      </div>
      {events.length ? (
        <Timeline
          events={events}
          plotline={plotline.id}
          goalsAt={placed.marks}
          focused={focusEvent}
          continuationTitle={
            plotline.continues_into_title ?? plotline.continues_into ?? null
          }
          onJump={jump}
        />
      ) : (
        <EmptyState icon="scenes" title="This thread has no scenes yet" />
      )}
    </div>
  );
}

export function PlotlineView({
  plotline,
  focusEvent,
}: {
  plotline: string;
  focusEvent: string | null;
}) {
  const { id: book, calendar } = useBookScope();
  const query = usePlotline(book, plotline, calendar);
  return (
    <Page label="Thread">
      <QueryState query={query}>
        {(data) => <Body plotline={data} focusEvent={focusEvent} />}
      </QueryState>
    </Page>
  );
}
