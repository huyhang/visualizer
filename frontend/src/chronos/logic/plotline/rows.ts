// What the editor draws for an order: the server's verdict when it is about
// this order, else the bare scenes, unjudged, while the verdict is on its way.
// Each of the thread's own scenes knows its place in the draft, so a move made
// on a row moves the right scene; inherited ones have no place to move from.

import type { EventSummary, PlotlinePreview } from "../../api/types";
import { timeframe } from "../text";
import { spanLabel } from "../timeaxis";

export interface OrderRow {
  id: string;
  title: string;
  when: string;
  owned: boolean;
  /** Position among the thread's own scenes; null for an inherited one. */
  index: number | null;
  scene: EventSummary;
}

function row(scene: EventSummary, index: number | null): OrderRow {
  return {
    id: scene.id,
    title: scene.title || scene.id,
    // Its end says only what changes, as on the Scenes cards.
    when: spanLabel(scene) ?? timeframe(scene),
    owned: scene.owned !== false,
    index,
    scene,
  };
}

export function displayRows(
  order: readonly string[],
  current: PlotlinePreview | null,
  known: ReadonlyMap<string, EventSummary>,
): OrderRow[] {
  if (current) {
    let own = 0;
    return current.effective_events.map((scene) =>
      row(scene, scene.owned === false ? null : own++),
    );
  }
  // Everything in the draft's order is the thread's own, whatever a previous
  // verdict called it; its findings are unknown until the next one arrives.
  return order.map((id, n) =>
    row({ ...(known.get(id) ?? { id }), owned: true, findings: [] }, n),
  );
}

/** Every scene a verdict or a pick has told us about, so a row can be named before it is judged. */
export function remember(
  known: Map<string, EventSummary>,
  scenes: Iterable<EventSummary>,
): Map<string, EventSummary> {
  const next = new Map(known);
  for (const scene of scenes) next.set(scene.id, { ...next.get(scene.id), ...scene });
  return next;
}
