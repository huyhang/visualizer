// A scene opened in place on the map: where, who, what happens, and the ways
// on -- beside the map in the inspector, or onto a thread's own timeline.
// Read once per scene and shared with the inspector's copy of it.

import type { EntityRef } from "../../api/types";
import { useEvent } from "../../hooks/queries";
import { timeframe } from "../../logic/text";
import { to } from "../../logic/route";
import { ArticleChip } from "../../components/common/Chips";
import { Link } from "../../components/common/Link";
import { useBookScope } from "../../components/shell/BookScope";
import { useInspector } from "../../components/shell/InspectorContext";
import { Button } from "../../../components/ui/Button";
import { Skeleton } from "../../../components/ui/Skeleton";

export function SceneDetails({ id, thread }: { id: string; thread: string | null }) {
  const { id: book, calendar } = useBookScope();
  const inspector = useInspector();
  const { data: scene, error } = useEvent(book, id, calendar);
  if (error) return <p className="cw-muted cw-small">This scene did not load.</p>;
  if (!scene) return <Skeleton lines={2} />;
  const open = (ref: EntityRef) => inspector.open({ kind: "article", ref });
  const cast = [scene.location, ...(scene.characters ?? []), ...(scene.items ?? [])];
  return (
    <div className="cw-map-card">
      <p className="cw-map-card-when">{timeframe(scene)}</p>
      <div className="cw-chip-row">
        {cast.map((ref) => (
          <ArticleChip
            key={`${ref.collection}/${ref.id}`}
            book={book}
            entity={ref}
            onOpen={open}
          />
        ))}
      </div>
      {scene.description ? <p className="cw-map-card-text">{scene.description}</p> : null}
      <div className="cw-map-card-actions">
        <Button
          size="sm"
          icon="panel"
          onClick={() => inspector.open({ kind: "scene", id })}
        >
          Open beside the map
        </Button>
        {thread ? (
          <Link
            className="st-btn st-btn-ghost st-btn-sm"
            to={to.plotline(book, thread, id)}
          >
            On its thread
          </Link>
        ) : null}
      </div>
    </div>
  );
}
