// When the scene happens, drawn: a Date/Tick choice where the book can be
// dated, the calendar to date it in where it keeps more than one, the boxes,
// and the server's reading of what was typed. Leaving everything empty is a
// fine answer -- a scene can be placed in time later.

import { useId } from "react";
import { DateFields } from "../../components/form/DateFields";
import { Field } from "../../components/form/Fields";
import type { Timing, TimingMode } from "./useTiming";

function ModeChoice({
  mode,
  onMode,
}: {
  mode: TimingMode;
  onMode: (mode: TimingMode) => void;
}) {
  return (
    <div className="cw-segmented" role="radiogroup" aria-label="Write the time as">
      {(["date", "tick"] as const).map((m) => (
        <button
          key={m}
          type="button"
          role="radio"
          aria-checked={mode === m}
          className={`cw-segment${mode === m ? " is-active" : ""}`}
          onClick={() => onMode(m)}
        >
          {m === "date" ? "Date" : "Tick"}
        </button>
      ))}
    </div>
  );
}

function TickBoxes({ timing }: { timing: Timing }) {
  const start = useId();
  const end = useId();
  return (
    <div className="cw-form-row">
      <Field label="Starts at (tick)" htmlFor={start}>
        <input
          id={start}
          className="st-input"
          inputMode="numeric"
          placeholder="e.g. 240"
          value={timing.startTick}
          onChange={(e) => timing.setStartTick(e.target.value)}
        />
      </Field>
      <Field label="Ends at (tick)" htmlFor={end}>
        <input
          id={end}
          className="st-input"
          inputMode="numeric"
          placeholder="e.g. 264"
          value={timing.endTick}
          onChange={(e) => timing.setEndTick(e.target.value)}
        />
      </Field>
    </div>
  );
}

function DateBoxes({ timing }: { timing: Timing }) {
  return (
    <div className="cw-scene-dates">
      <div className="cw-field">
        <span className="cw-field-label">Starts</span>
        <DateFields
          units={timing.units}
          value={timing.startDate}
          onChange={timing.setStartDate}
          label="Starts"
        />
      </div>
      <div className="cw-field">
        <span className="cw-field-label">Ends</span>
        <DateFields
          units={timing.units}
          value={timing.endDate}
          onChange={timing.setEndDate}
          label="Ends"
        />
      </div>
    </div>
  );
}

export function TimingField({ timing }: { timing: Timing }) {
  const pickId = useId();
  return (
    <fieldset className="cw-scene-timing">
      <legend className="cw-field-label">When</legend>
      <div className="cw-scene-timing-controls">
        {timing.units.length ? (
          <ModeChoice mode={timing.mode} onMode={timing.switchMode} />
        ) : null}
        {timing.calendars.length > 1 ? (
          <label className="cw-scene-calendar" htmlFor={pickId}>
            <span className="cw-muted cw-small">Dates in</span>
            <select
              id={pickId}
              className="st-input st-input-sm"
              value={timing.calendarId ?? ""}
              onChange={(e) => timing.switchCalendar(e.target.value)}
            >
              {timing.calendars.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.label || c.id}
                </option>
              ))}
            </select>
          </label>
        ) : null}
      </div>
      {timing.mode === "date" && timing.units.length ? (
        <DateBoxes timing={timing} />
      ) : (
        <TickBoxes timing={timing} />
      )}
      <p className="cw-scene-hint" aria-live="polite">
        {timing.hint}
      </p>
      {timing.readings.length ? (
        <ul className="cw-scene-readings">
          {timing.readings.map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
      ) : null}
      <p className="cw-field-hint">{timing.explanation}</p>
    </fieldset>
  );
}
