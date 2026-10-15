// From the book's story graph to what the map draws, in the classic page's
// four pure steps -- which threads, how dense, where everything goes, which
// goals land where -- recomputed only when one of their inputs changes.

import { useMemo } from "react";
import type { Graph } from "../../api/types";
import type { ThreadInfo } from "../../hooks/useThreads";
import {
  coverageOf,
  placeGoals,
  stripFor,
  type Placement,
  type UnplacedGoal,
} from "../../logic/goalPlacing";
import { collapseRuns, type Band } from "../../logic/map/collapse";
import { applyPeriodGrouping, type MapModel } from "../../logic/map/grouping";
import { geometry, layoutGraph } from "../../logic/map/layout";
import { threadsByNode } from "../../logic/map/selection";
import { restrictTo } from "../../logic/map/subgraph";
import { paletteColor } from "../../logic/threadColors";

export interface MapInputs {
  graph: Graph;
  selected: Set<string>;
  focusThread: string | null;
  openBands: Set<string>;
  closedMoments: Set<string>;
  compact: boolean;
  /** Book-wide paint, so a thread wears one colour in every view. */
  paintOf: (id: string) => ThreadInfo | undefined;
}

export interface MapDrawing {
  model: MapModel;
  bands: Band[];
  placement: Placement;
  strip: UnplacedGoal[];
  /** Every shown thread through each drawn node, for hover. */
  threadsAt: Map<string, Set<string>>;
  hasTerminus: boolean;
  hasUnscheduled: boolean;
}

export function rowHeight(compact: boolean): number {
  return compact ? geometry.ROW_COMPACT : geometry.ROW_H;
}

export function drawMap(inputs: MapInputs): MapDrawing {
  const { graph, selected, focusThread, openBands, closedMoments, compact, paintOf } =
    inputs;
  const slice = restrictTo(graph, selected, focusThread);
  const dense = collapseRuns(slice, { expanded: openBands });
  // After the fold, so a goal inside a folded run is marked on its band.
  const placement = placeGoals(graph.goals ?? [], coverageOf(dense.nodes));
  const heightOf = () => rowHeight(compact);
  const layout = layoutGraph(dense, {
    colorOf: (id) => paintOf(id)?.color ?? paletteColor(0),
    dashOf: (id) => paintOf(id)?.dash ?? "",
    heightOf,
  });
  return {
    model: applyPeriodGrouping(layout, { heightOf, collapsedMoments: closedMoments }),
    bands: dense.bands,
    placement,
    strip: stripFor(placement, slice.plotlines),
    threadsAt: threadsByNode(dense.plotlines),
    hasTerminus: layout.nodes.some((n) => n.isTerminus),
    hasUnscheduled: layout.hasUnscheduled,
  };
}

export function useMapModel(inputs: MapInputs): MapDrawing {
  const { graph, selected, focusThread, openBands, closedMoments, compact, paintOf } =
    inputs;
  return useMemo(
    () =>
      drawMap({ graph, selected, focusThread, openBands, closedMoments, compact, paintOf }),
    [graph, selected, focusThread, openBands, closedMoments, compact, paintOf],
  );
}
