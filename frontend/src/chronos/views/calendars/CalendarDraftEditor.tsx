// How a calendar counts, edited: invented cycles or Earth's months. Holds no
// state of its own -- the draft comes in and goes out -- so the library form
// owns what is being written.
//
// Switching kind replaces the draft outright rather than merging: a half-kept
// cycle list riding along inside an Earth calendar is exactly the leftover
// that gets saved by accident later.

import {
  GREGORIAN_TICK_UNITS,
  PRESETS,
  calendarHint,
  descriptorFrom,
  emptyCycle,
  type CalendarDraft,
  type CycleDraft,
} from "../../logic/calendars";
import { moveCycle } from "../../logic/books/calendarForm";
import { Field, SelectField, TextField } from "../../components/form/Fields";
import { Button, IconButton } from "../../../components/ui/Button";

type Invented = Extract<CalendarDraft, { kind: "mixed_radix" }>;

const capitalize = (word: string) => word.charAt(0).toUpperCase() + word.slice(1);

function CycleRow({
  cycle,
  index,
  count,
  onChange,
  onMove,
  onRemove,
}: {
  cycle: CycleDraft;
  index: number;
  count: number;
  onChange: (next: CycleDraft) => void;
  onMove: (delta: number) => void;
  onRemove: () => void;
}) {
  return (
    <li className="cw-cycle-row">
      <span className="cw-cycle-index">{index + 1}.</span>
      <input
        className="st-input st-input-sm"
        aria-label={`Cycle ${index + 1} name`}
        placeholder="day"
        value={cycle.name}
        onChange={(e) => onChange({ ...cycle, name: e.target.value })}
      />
      <span className="cw-muted cw-small">made of</span>
      <input
        className="st-input st-input-sm cw-cycle-size"
        aria-label={`Cycle ${index + 1} size`}
        inputMode="numeric"
        placeholder="24"
        value={cycle.size}
        onChange={(e) => onChange({ ...cycle, size: e.target.value })}
      />
      <IconButton
        icon="arrowUp"
        label="Move this cycle up"
        disabled={index === 0}
        onClick={() => onMove(-1)}
      />
      <IconButton
        icon="arrowDown"
        label="Move this cycle down"
        disabled={index === count - 1}
        onClick={() => onMove(1)}
      />
      <IconButton icon="x" label="Remove this cycle" onClick={onRemove} />
    </li>
  );
}

function InventedEditor({
  draft,
  onChange,
}: {
  draft: Invented;
  onChange: (next: CalendarDraft) => void;
}) {
  const setCycles = (cycles: CycleDraft[]) => onChange({ ...draft, cycles });
  return (
    <>
      <div className="cw-form-row">
        <TextField
          label="One tick is a…"
          value={draft.baseUnit}
          placeholder="hour"
          hint="The smallest unit your story counts in."
          onChange={(baseUnit) => onChange({ ...draft, baseUnit })}
        />
        <TextField
          label="Era (optional)"
          value={draft.epochLabel}
          placeholder="AF"
          hint="Appended to every label, e.g. “AF”."
          onChange={(epochLabel) => onChange({ ...draft, epochLabel })}
        />
      </div>
      <Field
        label="Cycles"
        hint="Smallest first: each counts how many of the unit below it make one of these."
      >
        <ol className="cw-cycle-list">
          {draft.cycles.map((cycle, n) => (
            <CycleRow
              key={n}
              cycle={cycle}
              index={n}
              count={draft.cycles.length}
              onChange={(next) =>
                setCycles(draft.cycles.map((c, i) => (i === n ? next : c)))
              }
              onMove={(delta) => setCycles(moveCycle(draft.cycles, n, delta))}
              onRemove={() => setCycles(draft.cycles.filter((_, i) => i !== n))}
            />
          ))}
        </ol>
      </Field>
      <div className="cw-chip-row">
        <Button
          size="sm"
          icon="plus"
          onClick={() => setCycles([...draft.cycles, emptyCycle()])}
        >
          Add a cycle
        </Button>
      </div>
      <Field label="Start from">
        <div className="cw-chip-row">
          {PRESETS.map((preset) => (
            <Button
              key={preset.key}
              size="sm"
              variant="ghost"
              onClick={() => onChange(preset.draft())}
            >
              {preset.label}
            </Button>
          ))}
        </div>
      </Field>
    </>
  );
}

export function CalendarDraftEditor({
  draft,
  onChange,
}: {
  draft: CalendarDraft;
  onChange: (next: CalendarDraft) => void;
}) {
  return (
    <div className="cw-calendar-draft">
      <SelectField
        label="What kind of calendar"
        value={draft.kind}
        hint="Earth's months are 28, 29, 30 or 31 days and are not yours to set."
        options={[
          { value: "mixed_radix", label: "Invented — fixed cycles" },
          { value: "gregorian", label: "Earth — Gregorian months" },
        ]}
        onChange={(kind) =>
          onChange(
            kind === "gregorian"
              ? { kind: "gregorian", tickUnit: "day" }
              : PRESETS[0]!.draft(),
          )
        }
      />
      {draft.kind === "gregorian" ? (
        <SelectField
          label="One tick is a…"
          value={draft.tickUnit}
          hint="The smallest unit your story counts in. Fixed, even though the months are not."
          options={GREGORIAN_TICK_UNITS.map((u) => ({ value: u, label: capitalize(u) }))}
          onChange={(tickUnit) => onChange({ kind: "gregorian", tickUnit })}
        />
      ) : (
        <InventedEditor draft={draft} onChange={onChange} />
      )}
      <p className="cw-calendar-reading" aria-live="polite">
        {calendarHint(descriptorFrom(draft))}
      </p>
    </div>
  );
}
