// The goals a view could not mark: what the shown threads pursue but that
// lands on no scene drawn here, each with the reason in words. Without it a
// thread pursuing four goals and marking one would read as a thread with one.

import type { UnplacedGoal } from "../../logic/goalPlacing";
import { MISSING } from "../../logic/goalPlacing";
import { Chip } from "./Chips";

export function UnplacedStrip({
  unplaced,
  onGoal,
  label = "Not landed here",
}: {
  unplaced: UnplacedGoal[];
  onGoal?: (id: string) => void;
  label?: string;
}) {
  if (!unplaced.length) return null;
  return (
    <section className="cw-unplaced" aria-label={label}>
      <h2 className="cw-section-title">{label}</h2>
      <ul className="cw-unplaced-list">
        {unplaced.map((g) => (
          <li key={g.id} className="cw-unplaced-item">
            <Chip
              tone={g.reason === MISSING ? "danger" : "muted"}
              icon="target"
              onClick={onGoal && g.reason !== MISSING ? () => onGoal(g.id) : undefined}
            >
              {g.title}
            </Chip>
            <span className="cw-muted cw-small">{g.note}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
