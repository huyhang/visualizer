// A date, typed in one calendar's own units: one box per unit, coarsest first,
// generated from the calendar -- so any invented calendar works with no
// per-calendar code here. Leaving the finer boxes blank names the whole period.

import { ERAS, type DateDraft, type DateUnit, type Era } from "../../logic/calendars";

const capitalize = (word: string) => word.charAt(0).toUpperCase() + word.slice(1);

export function DateFields({
  units,
  value,
  onChange,
  label,
}: {
  units: DateUnit[];
  value: DateDraft;
  onChange: (next: DateDraft) => void;
  /** What the whole date is, for screen readers: "Starts", "Ends". */
  label: string;
}) {
  const setPart = (name: string, text: string) =>
    onChange({ ...value, parts: { ...value.parts, [name]: text } });
  return (
    <div className="cw-date" role="group" aria-label={label}>
      {units.map((unit) => (
        <label key={unit.name} className="cw-date-part">
          <span className="cw-date-name">{capitalize(unit.name)}</span>
          <input
            className="st-input st-input-sm"
            inputMode="numeric"
            value={value.parts[unit.name] ?? ""}
            title={
              unit.max === null
                ? `${capitalize(unit.name)} — any whole number`
                : `${capitalize(unit.name)} ${unit.min}–${unit.max}`
            }
            onChange={(e) => setPart(unit.name, e.target.value)}
          />
          {unit.era ? (
            <select
              className="st-input st-input-sm cw-date-era"
              title="Before or after year 1"
              value={value.era}
              onChange={(e) => onChange({ ...value, era: e.target.value as Era })}
            >
              {ERAS.map((era) => (
                <option key={era} value={era}>
                  {era}
                </option>
              ))}
            </select>
          ) : null}
        </label>
      ))}
    </div>
  );
}
