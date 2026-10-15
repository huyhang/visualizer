// The book's scenes: a scrollable timeline of its clock by default, and the
// compact maintenance list one toggle away, both with the same writing,
// editing and removing actions. A scene used to be writable only from inside
// a thread, which left a scene abandoned mid-edit with no way to remove it;
// this is the book's own list, so a scene is something you can keep house on.
//
// It is a screen rather than a dialog because it is somewhere a writer goes
// and stays. The filter, page, view and clock position are remembered for the
// visit, so coming back lands where the writer left it.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { EventRow } from "../../api/types";
import { useApi } from "../../deps";
import { useTimeline } from "../../hooks/queries";
import { useSessionMemory } from "../../hooks/useSessionMemory";
import { useThreads, type Threads } from "../../hooks/useThreads";
import { SearchField, useDebounced } from "../../components/common/Fields";
import { Page, PageHeader } from "../../components/common/Page";
import { QueryState } from "../../components/common/QueryState";
import { useActions } from "../../components/shell/Actions";
import { useBookScope } from "../../components/shell/BookScope";
import { useInspector } from "../../components/shell/InspectorContext";
import { useLens } from "../../components/shell/Lens";
import { Button } from "../../../components/ui/Button";
import { EmptyState } from "../../../components/ui/EmptyState";
import { SceneCard, sceneTint } from "./SceneCard";
import { useSceneDeletion } from "./SceneDeletion";
import { SceneList } from "./SceneList";
import { SceneTimeline, railScenes, type Scheduled } from "./SceneTimeline";
import type { SceneActions } from "./SceneTools";

type Mode = "timeline" | "list";

const LEADS: Record<Mode, string> = {
  timeline:
    "Scroll through the book's clock. Scenes nearest the cursor come into view; undated scenes wait below.",
  list: "Every scene in this book, earliest first. Undated ones come last.",
};

function ModeToggle({ mode, onMode }: { mode: Mode; onMode: (mode: Mode) => void }) {
  return (
    <div className="cw-segmented" role="group" aria-label="Scene view">
      {(["timeline", "list"] as const).map((m) => (
        <button
          key={m}
          type="button"
          className={`cw-segment${mode === m ? " is-active" : ""}`}
          aria-pressed={mode === m}
          onClick={() => onMode(m)}
        >
          {m === "timeline" ? "Timeline" : "List"}
        </button>
      ))}
    </div>
  );
}

/** The scenes no clock can place yet, kept on a shelf under the rail. */
function UndatedShelf({
  scenes,
  card,
}: {
  scenes: EventRow[];
  card: (scene: EventRow) => React.ReactNode;
}) {
  if (!scenes.length) return null;
  return (
    <details className="cw-tl-undated">
      <summary>
        {scenes.length} unscheduled scene{scenes.length === 1 ? "" : "s"}
      </summary>
      <div className="cw-tl-undated-grid">
        {scenes.map((s) => (
          <div key={s.id}>{card(s)}</div>
        ))}
      </div>
    </details>
  );
}

function TimelineMode({
  filter,
  card,
  threads,
}: {
  filter: string;
  card: (scene: EventRow) => React.ReactNode;
  threads: Threads;
}) {
  const api = useApi();
  const { id: book, calendar } = useBookScope();
  const query = useTimeline(book, { filter, calendar });
  const [cursor, rememberCursor] = useSessionMemory<number | null>(
    `scenes:${book}:cursor`,
    null,
  );
  const [zoom, rememberZoom] = useSessionMemory(`scenes:${book}:zoom`, 1);
  // The cursor moves every frame; it is remembered only on the way out, not re-rendered into.
  const latest = useRef(cursor);
  useEffect(() => () => rememberCursor(latest.current), [rememberCursor]);
  const formatTick = useCallback(
    async (tick: number) => (await api.formatTicks(book, [tick], { calendar }))[0]?.label,
    [api, book, calendar],
  );
  const tint = useCallback(
    (scene: Scheduled) => sceneTint(scene.plotlines, threads),
    [threads],
  );
  return (
    <QueryState query={query} lines={8}>
      {(data) => {
        const events = railScenes(data.events);
        return (
          <div className="cw-tl-root">
            {events.length ? (
              <SceneTimeline
                key={`${filter}|${calendar}`}
                events={events}
                bounds={data.bounds}
                initialTick={cursor}
                initialZoom={zoom}
                onCursor={(tick) => {
                  latest.current = tick;
                }}
                onZoom={rememberZoom}
                formatTick={formatTick}
                renderCard={card}
                tintOf={tint}
              />
            ) : (
              <EmptyState
                icon="scenes"
                title={
                  data.unscheduled.length
                    ? "No dated scene matches"
                    : "No scenes match this view"
                }
              >
                {data.unscheduled.length
                  ? "The undated scenes are collected below."
                  : undefined}
              </EmptyState>
            )}
            <UndatedShelf scenes={data.unscheduled} card={card} />
          </div>
        );
      }}
    </QueryState>
  );
}

export function ScenesView() {
  const { id: book, book: record, canWrite, calendar } = useBookScope();
  const threads = useThreads(book);
  const inspector = useInspector();
  const lens = useLens();
  const { newScene, editScene } = useActions();
  const deletion = useSceneDeletion();
  const [mode, setMode] = useSessionMemory<Mode>(`scenes:${book}:mode`, "timeline");
  const [paging, setPaging] = useSessionMemory(`scenes:${book}:paging`, {
    filter: "",
    page: 1,
  });
  const [typed, setTyped] = useState(paging.filter);
  const filter = useDebounced(typed.trim());
  const page = paging.filter === filter ? paging.page : 1;
  // A filter typed and left is remembered on the way out, like the clock position.
  const latestPaging = useRef({ filter, page });
  useEffect(() => {
    latestPaging.current = { filter, page };
  }, [filter, page]);
  useEffect(() => () => setPaging(latestPaging.current), [setPaging]);

  const actions: SceneActions = useMemo(
    () => ({
      open: (id) => inspector.open({ kind: "scene", id }),
      edit: editScene,
      remove: deletion.start,
      canWrite,
      canDelete: Boolean(record?.permissions?.delete),
    }),
    [inspector, editScene, deletion.start, canWrite, record?.permissions?.delete],
  );
  const card = (scene: EventRow) => (
    <SceneCard
      book={book}
      scene={scene}
      threads={threads}
      terminus={record?.terminus}
      faded={lens.fades(scene.id)}
      actions={actions}
    />
  );
  const emptyText = filter
    ? `Nothing here contains every word of “${filter}”.`
    : canWrite
      ? "This book has no scenes yet — write the first one."
      : "This book has no scenes yet.";

  return (
    <Page label="Scenes" wide>
      <PageHeader
        eyebrow={record?.title || book}
        title="Scenes"
        subtitle={LEADS[mode]}
        actions={
          <>
            <ModeToggle mode={mode} onMode={setMode} />
            {canWrite && newScene ? (
              <Button variant="primary" icon="plus" onClick={() => newScene()}>
                New scene
              </Button>
            ) : null}
          </>
        }
      >
        <SearchField
          value={typed}
          onChange={setTyped}
          placeholder="Filter scenes…"
          label="Filter scenes"
        />
      </PageHeader>
      {mode === "timeline" ? (
        <TimelineMode filter={filter} card={card} threads={threads} />
      ) : (
        <SceneList
          book={book}
          filter={filter}
          page={page}
          onPage={(p) => setPaging({ filter, page: p })}
          calendar={calendar}
          threads={threads}
          terminus={record?.terminus}
          actions={actions}
          emptyText={emptyText}
        />
      )}
      {deletion.element}
    </Page>
  );
}
