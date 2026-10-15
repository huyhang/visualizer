// The server's verdict on a candidate order, asked for a moment after the
// writer stops changing it. The answer counts only while it is about what is
// on screen: a verdict on the order before the last drag is stale, and drawn
// as "checking" rather than trusted.

import { useEffect, useState } from "react";
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
  // The candidate as a value, so the effect depends on what it says, not on
  // which object happened to carry it this render.
  const asked = JSON.stringify(candidate);

  useEffect(() => {
    if (empty) return;
    let live = true;
    const timer = setTimeout(() => {
      api
        .previewPlotline(book, JSON.parse(asked), { calendar })
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
  }, [api, book, asked, key, calendar, empty]);

  const fresh = answer !== null && answer.key === key;
  return {
    current: !empty && fresh ? answer.preview : null,
    last: empty ? null : last,
    checking: !empty && !fresh,
    error: fresh ? answer.error : null,
  };
}
