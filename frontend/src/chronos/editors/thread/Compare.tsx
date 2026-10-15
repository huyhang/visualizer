// Trying another order, side by side: what the server makes of each
// arrangement, and which holds together better. Nothing is saved until the
// writer keeps one and presses Save -- comparing is free.

import type { PlotlinePreview } from "../../api/types";
import {
  better,
  headline,
  summarize,
  type OrderSummary,
} from "../../logic/plotline/compare";
import type { Side } from "../../logic/plotline/editing";
import { Button } from "../../../components/ui/Button";
import { Icon } from "../../../components/ui/Icon";

function Facts({ summary }: { summary: OrderSummary }) {
  return (
    <ul className="cw-compare-facts">
      <li className={summary.reachesEnding ? "is-ok" : "is-bad"}>
        <Icon name={summary.reachesEnding ? "check" : "alert"} size={13} />
        {summary.reachesEnding ? "Reaches the ending" : "Stops before the ending"}
      </li>
      <li className={summary.continuationHolds ? "is-ok" : "is-bad"}>
        <Icon name={summary.continuationHolds ? "check" : "alert"} size={13} />
        {summary.continuationHolds ? "Continuation holds" : "Continuation breaks"}
      </li>
      <li className={summary.troubled.length ? "is-bad" : "is-ok"}>
        <Icon name={summary.troubled.length ? "alert" : "check"} size={13} />
        {summary.troubled.length
          ? `${summary.troubled.length} scene${summary.troubled.length === 1 ? "" : "s"} in trouble`
          : "Every scene sound"}
      </li>
    </ul>
  );
}

function Card({
  side,
  name,
  preview,
  winner,
  onKeep,
}: {
  side: Side;
  name: string;
  preview: PlotlinePreview | null;
  winner: boolean;
  onKeep: () => void;
}) {
  const summary = preview ? summarize(preview) : null;
  return (
    <div className={`cw-compare-card${winner ? " is-better" : ""}`}>
      <div className="cw-compare-card-head">
        <span className="cw-compare-side" aria-hidden="true">
          {side}
        </span>
        <span className="cw-compare-name">{name}</span>
        {winner ? <span className="cw-compare-better">Holds together better</span> : null}
      </div>
      <div className={`cw-compare-headline${summary?.problems ? " is-bad" : ""}`}>
        {summary ? headline(summary) : "Checking…"}
      </div>
      {summary ? <Facts summary={summary} /> : null}
      <Button size="sm" variant={winner ? "primary" : "secondary"} onClick={onKeep}>
        Keep {side}
      </Button>
    </div>
  );
}

export function CompareBar({
  a,
  b,
  onKeep,
}: {
  a: PlotlinePreview | null;
  b: PlotlinePreview | null;
  onKeep: (side: Side) => void;
}) {
  const verdict = a && b ? better(summarize(a), summarize(b)) : "even";
  return (
    <div className="cw-compare" role="group" aria-label="Compare the two orders">
      <Card
        side="A"
        name="Current order"
        preview={a}
        winner={verdict === "A"}
        onKeep={() => onKeep("A")}
      />
      <div className="cw-compare-vs" aria-hidden="true">
        vs
      </div>
      <Card
        side="B"
        name="Alternative"
        preview={b}
        winner={verdict === "B"}
        onKeep={() => onKeep("B")}
      />
    </div>
  );
}
