// The story map: pick any number of the book's threads and see how they weave.
//
// This is the shell -- data, picker, state -- around the four pure steps in
// logic/map (which threads, how dense, where everything goes, which goals land
// where). "Connected plots" is a preset of it, not a screen of its own:
// arriving from a thread selects that thread and everything it meets, then the
// address is rewritten to the selection it stands for.
//
// State worth a link (which threads) lives in the address; state worth only
// the visit (open scenes, density, goal marks) lives in session memory, and
// survives a re-slice -- ticking a thread on must not shut the scene you were reading.

import { useEffect, useRef, useState, type RefObject } from "react";
import type { Graph } from "../../api/types";
import { useGraph } from "../../hooks/queries";
import { useSessionMemory } from "../../hooks/useSessionMemory";
import { useThreads, type ThreadInfo } from "../../hooks/useThreads";
import type { LaidNode } from "../../logic/map/layout";
import { footnote } from "../../logic/map/selection";
import { EntityName } from "../../components/common/EntityName";
import { Page, PageHeader } from "../../components/common/Page";
import { QueryState } from "../../components/common/QueryState";
import { UnplacedStrip } from "../../components/common/UnplacedStrip";
import { useBookScope } from "../../components/shell/BookScope";
import { useInspector } from "../../components/shell/InspectorContext";
import { useLens, type Lens } from "../../components/shell/Lens";
import { EmptyState } from "../../../components/ui/EmptyState";
import { Icon } from "../../../components/ui/Icon";
import { RowControlsProvider, sceneCount, type RowControls } from "./MapRows";
import { StoryGraph } from "./StoryGraph";
import { ThreadPicker } from "./ThreadPicker";
import { useMapModel } from "./useMapModel";
import { useMapSelection, type MapAddress, type MapSelection } from "./useMapSelection";
import { useToggleSet } from "./useToggleSet";

export interface MapViewProps {
  selection: string[];
  connectedFrom: string | null;
  focusEvent: string | null;
}

/** Whether the lens fades a drawn node: a band fades only when every scene in it does. */
export function nodeFades(
  lens: Pick<Lens, "fades">,
  node: Pick<LaidNode, "id" | "isBand" | "events">,
): boolean {
  return node.isBand
    ? (node.events ?? []).every((id) => lens.fades(id))
    : lens.fades(node.id);
}

function SelectionNote({ selection, total }: { selection: MapSelection; total: number }) {
  const shown = selection.selected.size;
  if (shown === total) return <span>Every thread in this book — {total}.</span>;
  return (
    <span>
      {shown} of {total} threads — {total - shown} not shown ·{" "}
      <button
        type="button"
        className="cw-link-btn"
        onClick={selection.all}
        title="Add the threads this selection leaves out"
      >
        Show all
      </button>
    </span>
  );
}

function LensNote({ graph, selected }: { graph: Graph; selected: Set<string> }) {
  const { id: book } = useBookScope();
  const lens = useLens();
  if (!lens.subject || !lens.featured) return null;
  const scenes = new Set(
    graph.plotlines.filter((p) => selected.has(p.id)).flatMap((p) => p.effective_events),
  );
  const featured = [...scenes].filter((id) => lens.featured?.has(id)).length;
  return (
    <p className="cw-map-lens" role="status">
      <Icon name="lens" size={15} /> Following{" "}
      <strong>
        <EntityName book={book} entity={lens.subject} />
      </strong>{" "}
      — {sceneCount(featured, scenes.size)}
    </p>
  );
}

/** Bring the scene the map was opened at into view, once, after it is drawn. */
function useScrollTo(container: RefObject<HTMLElement | null>, scene: string | null) {
  const done = useRef(false);
  useEffect(() => {
    if (!scene || done.current) return;
    const row = container.current?.querySelector(`[data-scene="${CSS.escape(scene)}"]`);
    if (row) {
      done.current = true;
      row.scrollIntoView({ block: "center" });
    }
  });
}

function StoryMap({
  graph,
  address,
  focusEvent,
}: {
  graph: Graph;
  address: MapAddress;
  focusEvent: string | null;
}) {
  const { id: book, calendar } = useBookScope();
  const threads = useThreads(book, calendar);
  const inspector = useInspector();
  const lens = useLens();
  const selection = useMapSelection(book, graph, address);
  const open = useToggleSet(`map:${book}:open`);
  const bands = useToggleSet(`map:${book}:bands`);
  const moments = useToggleSet(`map:${book}:moments`);
  const marks = useToggleSet(`map:${book}:marks`);
  const [compact, setCompact] = useSessionMemory(`map:${book}:compact`, false);
  const [showGoals, setShowGoals] = useSessionMemory(`map:${book}:goals`, true);
  const [hot, setHot] = useState<Set<string> | null>(null);
  const body = useRef<HTMLDivElement>(null);
  useScrollTo(body, focusEvent);

  const drawing = useMapModel({
    graph,
    selected: selection.selected,
    focusThread: selection.focusThread,
    openBands: bands.ids,
    closedMoments: moments.ids,
    compact,
    paintOf: threads.get,
  });
  const fades = (node: LaidNode) => nodeFades(lens, node);
  const controls: RowControls = {
    isOpen: open.has,
    toggleScene: open.toggle,
    unfold: bands.toggle,
    toggleMoment: moments.toggle,
    marksOpen: marks.has,
    toggleMarks: marks.toggle,
    inspectScene: (id) => inspector.open({ kind: "scene", id }),
    openGoal: (id) => inspector.open({ kind: "goal", id }),
    goalsAt: showGoals ? drawing.placement.marks : new Map(),
    focusEvent,
    fades,
    homeThread: (id) => [...(drawing.threadsAt.get(id) ?? [])][0] ?? null,
    hover: (id) => setHot(id ? (drawing.threadsAt.get(id) ?? null) : null),
  };
  const folded = drawing.bands.filter((b) => !bands.has(b.id));
  const shownThreads = threads.list.length
    ? threads.list
    : graph.plotlines.map(fallbackPaint);

  return (
    <div ref={body} className={`cw-map${compact ? " is-compact" : ""}`}>
      <p className="cw-map-note">
        <SelectionNote selection={selection} total={graph.plotlines.length} />
      </p>
      <LensNote graph={graph} selected={selection.selected} />
      <ThreadPicker
        threads={shownThreads}
        selected={selection.selected}
        onToggle={selection.toggle}
        onAll={selection.all}
        onNone={selection.none}
        onInvert={selection.invert}
        compact={compact}
        onCompact={() => setCompact(!compact)}
        showGoals={showGoals}
        onGoals={() => setShowGoals(!showGoals)}
        canFold={drawing.bands.length > 0}
        unfolded={drawing.bands.length > 0 && folded.length === 0}
        onFold={() => bands.set(folded.length ? drawing.bands.map((b) => b.id) : [])}
        onHover={(id) => setHot(id ? new Set([id]) : null)}
      />
      {selection.selected.size === 0 ? (
        <EmptyState icon="map" title="No threads selected">
          Tick a thread above to start the map.
        </EmptyState>
      ) : (
        <>
          {showGoals ? (
            <UnplacedStrip
              unplaced={drawing.strip}
              onGoal={controls.openGoal}
              label="Not landed on the shown threads"
            />
          ) : null}
          <RowControlsProvider value={controls}>
            <StoryGraph
              model={drawing.model}
              hot={hot}
              threadsAt={drawing.threadsAt}
              fades={fades}
            />
          </RowControlsProvider>
          <p className="cw-map-foot">
            {footnote({
              folded: folded.length,
              hidden: folded.reduce((n, b) => n + b.events.length, 0),
              hasTerminus: drawing.hasTerminus,
              hasUnscheduled: drawing.hasUnscheduled,
            })}
          </p>
        </>
      )}
    </div>
  );
}

/** Before the shared thread list arrives, threads still need a mark. */
function fallbackPaint(p: Graph["plotlines"][number]): ThreadInfo {
  return { id: p.id, title: p.title || p.id, color: "var(--muted)", dash: "", turn: 0 };
}

export function MapView({ selection, connectedFrom, focusEvent }: MapViewProps) {
  const { id: book, book: record, calendar } = useBookScope();
  const query = useGraph(book, calendar);
  // The scene the map was opened at outlives the address rewrite that drops it.
  const [arrivedAt] = useState(focusEvent);
  return (
    <Page label="Story map" wide>
      <PageHeader
        eyebrow={record?.title || book}
        title="Story map"
        subtitle="Pick any number of threads and see how they weave — where they split, where they meet, in time order."
      />
      <QueryState query={query}>
        {(graph) =>
          graph.plotlines.length ? (
            <StoryMap
              graph={graph}
              address={{ selection, connectedFrom }}
              focusEvent={focusEvent ?? arrivedAt}
            />
          ) : (
            <EmptyState icon="map" title="Nothing to map yet">
              This book has no threads yet, so there is nothing to weave.
            </EmptyState>
          )
        }
      </QueryState>
    </Page>
  );
}
