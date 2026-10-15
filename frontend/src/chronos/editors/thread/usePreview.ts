// The server's verdict on a candidate order, asked for a moment after the
// writer stops changing it. The answer counts only while it is about what is
// on screen: a verdict on the order before the last drag is stale, and drawn
// as "checking" rather than trusted.

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import type { PlotlinePreview, PlotlineWrite } from "../../api/types";
import { messageOf } from "../../api/errors";
import { useApi } from "../../deps";

export const PREVIEW_DEBOUNCE_MS = 250;

export interface Preview {
  /** The verdict, when it is about the candidate on screen. */
  current: PlotlinePreview | null;
  /** The last verdict that came back, current or not: rows to draw while re-checking. */
  last: PlotlinePreview | null;
  checking: boolean;
  error: string | null;
}

interface Answer {
  key: string;
  preview: PlotlinePreview | null;
  error: string | null;
}

export function usePreview(
  book: string,
  candidate: PlotlineWrite & { id?: string },
  key: string,
  calendar: string | null,
): Preview {
  const api = useApi();
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [last, setLast] = useState<PlotlinePreview | null>(null);
  const empty = candidate.events.length === 0;
  // Asked again when `key` -- what can change the verdict -- changes, with the
  // candidate as it stands then: typing a title is not a reason to re-judge.
  const latest = useRef(candidate);
  useLayoutEffect(() => {
    latest.current = candidate;
  });

  useEffect(() => {
    if (empty) return;
    let live = true;
    const timer = setTimeout(() => {
      api
        .previewPlotline(book, latest.current, { calendar })
        .then((preview) => {
          if (!live) return;
          setAnswer({ key, preview, error: null });
          setLast(preview);
        })
        .catch(
          (e: unknown) =>
            live &&
            setAnswer({
              key,
              preview: null,
              error: messageOf(e, "Could not check this order."),
            }),
        );
    }, PREVIEW_DEBOUNCE_MS);
    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, [api, book, key, calendar, empty]);

  const fresh = answer !== null && answer.key === key;
  return {
    current: !empty && fresh ? answer.preview : null,
    last: empty ? null : last,
    checking: !empty && !fresh,
    error: fresh ? answer.error : null,
  };
}
