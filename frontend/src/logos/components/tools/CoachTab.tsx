// The Writing Coach's findings: local rules, nothing sent anywhere. Each one
// is underlined in the prose too; here they are listed, with the dialect they
// were checked against.

import type { Dialect } from "../../api/types";
import { Icon } from "../../../components/ui/Icon";
import { Spinner } from "../../../components/ui/Spinner";
import type { Placement } from "../../editor/annotations";
import type { Coach } from "../../hooks/useCoach";
import { coachNote, type NoteActions } from "../../logic/notes";
import { NoteCard } from "../review/NoteCard";
import { LayerToggle } from "./LayerToggle";

export function CoachTab({
  coach,
  placement,
  actions,
  marked,
  onMarked,
}: {
  coach: Coach;
  placement: Placement;
  actions: NoteActions;
  marked: boolean;
  onMarked: (marked: boolean) => void;
}) {
  return (
    <div className="lw-stack">
      <div className="lw-coach-head">
        <label className="lw-dialect">
          <span>English</span>
          <select
            value={coach.dialect}
            onChange={(event) => coach.setDialect(event.target.value as Dialect)}
          >
            <option value="en-US">US</option>
            <option value="en-GB">UK</option>
          </select>
        </label>
        <LayerToggle
          label="Underline in the manuscript"
          checked={marked}
          onChange={onMarked}
        />
      </div>
      {coach.error ? <p className="st-error-text">{coach.error}</p> : null}
      {coach.loading ? (
        <p className="lw-muted lw-inline">
          <Spinner size={14} /> Reading locally…
        </p>
      ) : coach.issues.length ? (
        coach.issues.map((issue) => {
          const note = coachNote(issue);
          return (
            <NoteCard
              key={issue.id}
              note={note}
              actions={actions}
              placed={placement[note.id] != null}
              variant="detail"
            />
          );
        })
      ) : !coach.error ? (
        <div className="lw-empty is-clear">
          <span className="lw-empty-icon">
            <Icon name="check" size={20} />
          </span>
          <p>No local suggestions. Keep writing.</p>
        </div>
      ) : null}
    </div>
  );
}
