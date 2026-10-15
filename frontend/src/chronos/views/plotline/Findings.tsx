// What the server says is wrong with a thread, drawn the same in the timeline
// and in the editor: each scene's findings, the banner naming the scenes in
// trouble, and the whole-thread verdicts no single scene can carry.

import type { EventFinding, EventSummary, PlotlineStatus } from "../../api/types";
import { conflictCount, problemScenes, verdictNotes } from "../../logic/plotline/verdicts";
import { plural } from "../../logic/text";
import { FindingText } from "../../components/common/FindingText";
import { Icon } from "../../../components/ui/Icon";

function FindingRow({
  book,
  finding,
  onJump,
}: {
  book: string;
  finding: EventFinding;
  onJump?: (scene: string) => void;
}) {
  const conflict = finding.severity === "conflict";
  return (
    <li className={`cw-pl-finding is-${conflict ? "conflict" : "hint"}`}>
      <span className="cw-pl-finding-mark" aria-hidden="true">
        {conflict ? "!" : "i"}
      </span>
      <span className="cw-pl-finding-text">
        <FindingText book={book} message={finding.message} refs={finding.refs} />
      </span>
      {onJump
        ? finding.events.map((other) => (
            <button
              key={other}
              type="button"
              className="cw-pl-finding-jump"
              title={`Go to ${other}`}
              onClick={() => onJump(other)}
            >
              show
            </button>
          ))
        : null}
    </li>
  );
}

/** Every finding on one scene, or nothing when it is sound. */
export function FindingList({
  book,
  scene,
  onJump,
}: {
  book: string;
  scene: Pick<EventSummary, "findings">;
  onJump?: (scene: string) => void;
}) {
  const findings = scene.findings ?? [];
  if (!findings.length) return null;
  return (
    <ul className="cw-pl-findings">
      {findings.map((f, n) => (
        <FindingRow key={`${f.code}-${n}`} book={book} finding={f} onJump={onJump} />
      ))}
    </ul>
  );
}

/** How many problems, and where. Absent for a sound thread: its absence is the signal. */
export function ProblemBanner({
  events,
  status,
  onJump,
  noun = "thread",
}: {
  events: EventSummary[];
  status: PlotlineStatus | undefined;
  onJump: (scene: string) => void;
  noun?: string;
}) {
  const count = conflictCount(status);
  if (!count) return null;
  return (
    <div className="cw-pl-banner" role="status">
      <div className="cw-pl-banner-head">
        <Icon name="alert" size={16} />
        <strong>
          {plural(count, "problem")} in this {noun}
        </strong>
      </div>
      <div className="cw-chip-row">
        {problemScenes(events).map((s) => (
          <button
            key={s.id}
            type="button"
            className="cw-pl-banner-link"
            title="Go to this scene"
            onClick={() => onJump(s.id)}
          >
            {s.title || s.id}
          </button>
        ))}
      </div>
    </div>
  );
}

/** A broken continuation, or a thread that never reaches the ending. */
export function VerdictNotes({
  status,
  events,
}: {
  status: PlotlineStatus | undefined;
  events: EventSummary[];
}) {
  const notes = verdictNotes(status, events);
  if (!notes.length) return null;
  return (
    <ul className="cw-pl-findings cw-pl-verdicts">
      {notes.map((note) => (
        <li key={note} className="cw-pl-finding is-hint">
          <span className="cw-pl-finding-mark" aria-hidden="true">
            i
          </span>
          <span className="cw-pl-finding-text">{note}</span>
        </li>
      ))}
    </ul>
  );
}
