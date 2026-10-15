// Inputs the screens share: a filter box, and the "Dates in" calendar picker.

import { useEffect, useState } from "react";
import type { CalendarAttachment } from "../../api/types";
import { eraNote } from "../../logic/calendarView";
import { Icon } from "../../../components/ui/Icon";

/** `value`, once it has stopped changing for `ms`. */
export function useDebounced<T>(value: T, ms = 250): T {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setSettled(value), ms);
    return () => clearTimeout(timer);
  }, [value, ms]);
  return settled;
}

export function SearchField({
  value,
  onChange,
  placeholder,
  label,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  label: string;
}) {
  return (
    <label className="cw-search">
      <Icon name="search" size={15} />
      <input
        type="search"
        className="cw-search-input"
        value={value}
        placeholder={placeholder}
        aria-label={label}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  );
}

/** Absent unless there is a real choice: most books keep one calendar. */
export function CalendarSwitcher({
  calendars,
  value,
  onChange,
}: {
  calendars: CalendarAttachment[];
  value: string | null;
  onChange: (id: string) => void;
}) {
  if (calendars.length < 2) return null;
  return (
    <label className="cw-calendar-switch">
      <span className="cw-calendar-switch-label">
        <Icon name="calendar" size={14} /> Dates in
      </span>
      <select
        className="st-input st-input-sm"
        aria-label="Read dates in"
        value={value ?? calendars[0]?.id}
        onChange={(e) => onChange(e.target.value)}
      >
        {calendars.map((c) => (
          <option key={c.id} value={c.id} title={eraNote(c) || undefined}>
            {c.label || c.id}
          </option>
        ))}
      </select>
    </label>
  );
}
