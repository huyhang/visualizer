// The compact maintenance list: every scene in the book, earliest first,
// undated ones last, paged on the server. The place to keep house -- a scene
// in no thread yet, or one abandoned mid-edit, is findable here.

import type { EventRow } from "../../api/types";
import { useEvents } from "../../hooks/queries";
import type { Threads } from "../../hooks/useThreads";
import { plural } from "../../logic/text";
import { Chip } from "../../components/common/Chips";
import { Pager } from "../../components/common/Pager";
import { QueryState } from "../../components/common/QueryState";
import { useLens } from "../../components/shell/Lens";
import { Badge } from "../../../components/ui/Badge";
import { EmptyState } from "../../../components/ui/EmptyState";
import { Place, UsedBy } from "./SceneCard";
import { SceneTools, type SceneActions } from "./SceneTools";

/** A span reads as its start, then "→ its end" beneath: two lines that never wrap mid-date. */
export function whenLines(when: string): string[] {
  const [start, end] = when.split(" → ");
  return end === undefined ? [when] : [start ?? when, `→ ${end}`];
}

const PER_PAGE = 20;

function Row({
  book,
  scene,
  threads,
  terminus,
  actions,
}: {
  book: string;
  scene: EventRow;
  threads: Threads;
  terminus?: string | null;
  actions: SceneActions;
}) {
  const { fades } = useLens();
  return (
    <li className={`cw-scene-row${fades(scene.id) ? " cw-faded" : ""}`}>
      <span className="cw-scene-row-when">
        {whenLines(scene.when).map((line, n) => (
          <span key={n} className="cw-scene-row-when-line">
            {line}
          </span>
        ))}
      </span>
      <span className="cw-scene-row-name">
        <button
          type="button"
          className="cw-scene-card-title"
          onClick={() => actions.open(scene.id)}
        >
          {scene.title}
        </button>
        {scene.id === terminus ? <Badge tone="warn">Ending</Badge> : null}
        {scene.scheduled ? null : <Chip tone="muted">unscheduled</Chip>}
      </span>
      <Place book={book} scene={scene} />
      <UsedBy plotlines={scene.plotlines} threads={threads} />
      <SceneTools scene={scene} actions={actions} />
    </li>
  );
}

export function SceneList({
  book,
  filter,
  page,
  onPage,
  calendar,
  threads,
  terminus,
  actions,
  emptyText,
}: {
  book: string;
  filter: string;
  page: number;
  onPage: (page: number) => void;
  calendar: string | null;
  threads: Threads;
  terminus?: string | null;
  actions: SceneActions;
  emptyText: string;
}) {
  const query = useEvents(book, { filter, page, perPage: PER_PAGE, calendar });
  return (
    <QueryState query={query}>
      {(data) =>
        data.events.length ? (
          <>
            <div className="cw-scene-list-head" aria-hidden="true">
              <span>When</span>
              <span>Scene</span>
              <span>Place</span>
              <span>Threads</span>
              <span />
            </div>
            <ul className="cw-scene-list" aria-label="Scenes">
              {data.events.map((scene) => (
                <Row
                  key={scene.id}
                  book={book}
                  scene={scene}
                  threads={threads}
                  terminus={terminus}
                  actions={actions}
                />
              ))}
            </ul>
            <Pager
              page={data.page}
              pages={data.pages}
              total={plural(data.total, "scene")}
              onPage={onPage}
            />
          </>
        ) : (
          <EmptyState icon="scenes" title={filter ? "No scene matches" : "No scenes yet"}>
            {emptyText}
          </EmptyState>
        )
      }
    </QueryState>
  );
}
