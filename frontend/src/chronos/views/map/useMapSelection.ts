// Which threads are on the map, kept in step with the address.
//
// The selection is worth a link, so every change is written to the URL -- as a
// replacement, not a new history entry, so Back leaves the map rather than
// undoing ticks. Arriving on the "connected" preset rewrites the URL to the
// selection it stands for, so what gets shared is the selection, not how you
// got there. If the address changes under the map (the palette, Back), the
// map follows it.

import { useCallback, useEffect, useMemo, useState } from "react";
import type { Graph } from "../../api/types";
import { useRoute } from "../../hooks/useRoute";
import { to } from "../../logic/route";
import {
  initialSelection,
  inverted,
  toggled,
  urlSelection,
} from "../../logic/map/selection";

export interface MapAddress {
  selection: string[];
  connectedFrom: string | null;
}

export interface MapSelection {
  bookOrder: string[];
  selected: Set<string>;
  /** The thread the writer arrived from, until they start steering. */
  focusThread: string | null;
  toggle: (id: string) => void;
  all: () => void;
  none: () => void;
  invert: () => void;
}

const addressKey = ({ selection, connectedFrom }: MapAddress) =>
  connectedFrom ? `connected:${connectedFrom}` : selection.join(",");

export function useMapSelection(
  book: string,
  graph: Graph,
  address: MapAddress,
): MapSelection {
  const { replace } = useRoute();
  const bookOrder = useMemo(() => graph.plotlines.map((p) => p.id), [graph]);
  const known = (id: string | null) => (id && bookOrder.includes(id) ? id : null);
  const [selected, setSelected] = useState(() =>
    initialSelection(graph, address.selection, address.connectedFrom),
  );
  const [focusThread, setFocusThread] = useState(() => known(address.connectedFrom));
  // What this map last wrote, and the address it last saw, so a change it made
  // is told apart from one made under it.
  const [written, setWritten] = useState(() => urlSelection(bookOrder, selected).join(","));
  const [seen, setSeen] = useState(() => addressKey(address));

  const key = addressKey(address);
  if (key !== seen) {
    setSeen(key);
    if (key !== written) {
      const next = initialSelection(graph, address.selection, address.connectedFrom);
      setSelected(next);
      setFocusThread(known(address.connectedFrom));
      setWritten(urlSelection(bookOrder, next).join(","));
    }
  }

  // The preset is how the map was entered; the URL should say what it became.
  useEffect(() => {
    if (address.connectedFrom) replace(to.map(book, written ? written.split(",") : []));
  }, [address.connectedFrom, book, written, replace]);

  const commit = useCallback(
    (next: Set<string>) => {
      const ids = urlSelection(bookOrder, next);
      setSelected(next);
      setFocusThread(null);
      setWritten(ids.join(","));
      replace(to.map(book, ids));
    },
    [book, bookOrder, replace],
  );

  return {
    bookOrder,
    selected,
    focusThread,
    toggle: (id) => commit(toggled(selected, id)),
    all: () => commit(new Set(bookOrder)),
    none: () => commit(new Set()),
    invert: () => commit(inverted(bookOrder, selected)),
  };
}
