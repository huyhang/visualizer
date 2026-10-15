// The timing section's state and behaviour: two spellings of one timeframe
// (ticks, or dates in one of the book's calendars), a live hint from the
// server, and the carrying of a timeframe across when either the spelling or
// the calendar changes -- without which the hidden spelling keeps whatever it
// held when the form opened, and a save from the other side silently loses
// the edit. Ported from the classic scenetiming.js; the server does every
// conversion, the browser none.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { CalendarAttachment, CalendarDescriptor, SceneEvent } from "../../api/types";
import { messageOf } from "../../api/errors";
import { useApi } from "../../deps";
import {
  calendarHint,
  dateDraft,
  dateUnits,
  emptyDate,
  type DateDraft,
  type DateUnit,
} from "../../logic/calendars";
import {
  UNSCHEDULED_HINT,
  dateBody,
  dateTicksFor,
  describeDates,
  describeTicks,
  intOrNull,
  labelsAreUseful,
  readingsAt,
  tickBody,
  withNulls,
  type Read,
  type TimeframeBody,
} from "../../logic/scenes/timing";

export type TimingMode = "date" | "tick";
const DEBOUNCE_MS = 250;

export interface Timing {
  mode: TimingMode;
  calendars: CalendarAttachment[];
  calendarId: string | null;
  units: DateUnit[];
  startTick: string;
  endTick: string;
  startDate: DateDraft;
  endDate: DateDraft;
  hint: string;
  readings: string[];
  /** The plain-language reading of the chosen calendar. */
  explanation: string;
  setStartTick: (text: string) => void;
  setEndTick: (text: string) => void;
  setStartDate: (date: DateDraft) => void;
  setEndDate: (date: DateDraft) => void;
  switchMode: (mode: TimingMode) => void;
  switchCalendar: (id: string) => void;
  /** What to send and through which calendar, or why it cannot be sent yet. */
  timeframe: () => Read<TimeframeBody> & { calendar?: string | null };
}

interface Ticks {
  start: number;
  end: number;
}

const attachmentOf = (calendars: CalendarAttachment[], id: string | null) =>
  calendars.find((c) => c.id === id) ?? calendars[0] ?? null;

export function useTiming(
  book: string,
  calendars: CalendarAttachment[],
  initialCalendar: string | null,
  event: SceneEvent | null,
): Timing {
  const api = useApi();
  const [calendarId, setCalendarId] = useState<string | null>(
    () => attachmentOf(calendars, initialCalendar)?.id ?? null,
  );
  const descriptor: CalendarDescriptor | null =
    attachmentOf(calendars, calendarId)?.descriptor ?? null;
  const units = useMemo(() => dateUnits(descriptor), [descriptor]);
  const scheduled =
    event !== null &&
    typeof event.start_tick === "number" &&
    typeof event.end_tick === "number";
  const [mode, setMode] = useState<TimingMode>(units.length ? "date" : "tick");
  const [startTick, setStartTick] = useState(scheduled ? String(event.start_tick) : "");
  const [endTick, setEndTick] = useState(scheduled ? String(event.end_tick) : "");
  const [startDate, setStartDate] = useState<DateDraft>(emptyDate);
  const [endDate, setEndDate] = useState<DateDraft>(emptyDate);
  const [hint, setHint] = useState("");
  const [readings, setReadings] = useState<string[]>([]);
  // The last timeframe known in ticks, so a change of calendar re-expresses the same moment.
  const lastTicks = useRef<Ticks | null>(
    scheduled ? { start: event.start_tick as number, end: event.end_tick as number } : null,
  );
  // What the writer has typed, counted, and the count when a conversion set
  // off (null when none is on its way). A conversion that comes back after
  // they typed leaves their input alone; a save while one is still on its way
  // takes the ticks the form already knows, not the boxes still being filled.
  const edits = useRef(0);
  const carrying = useRef<number | null>(null);
  const typed =
    <T>(set: (value: T) => void) =>
    (value: T) => {
      edits.current += 1;
      set(value);
    };
  const carry = useCallback(async (work: (stale: () => boolean) => Promise<void>) => {
    const since = edits.current;
    carrying.current = since;
    try {
      await work(() => edits.current !== since);
    } finally {
      if (carrying.current === since) carrying.current = null;
    }
  }, []);

  /**
   * Show a known timeframe in date boxes. A reckoning not kept then has no date
   * for these ticks, so rather than blank boxes -- which would un-schedule the
   * scene on save -- the form drops to ticks holding the ticks themselves.
   */
  const showTicksAsDate = useCallback(
    (ticks: Ticks, inUnits: DateUnit[], inCalendar: string | null) =>
      carry(async (stale) => {
        setStartTick(String(ticks.start));
        setEndTick(String(ticks.end));
        const pair = dateTicksFor(ticks.start, ticks.end);
        if (!inUnits.length || !pair) return setMode("tick");
        try {
          const labels = await api.formatTicks(book, pair, { calendar: inCalendar });
          if (stale()) return;
          const at = (tick: number) =>
            labels.find((t) => t.tick === tick)?.components ?? null;
          const from = at(pair[0]);
          const to = at(pair[1]);
          if (from && to) {
            setStartDate(dateDraft(inUnits, from));
            setEndDate(dateDraft(inUnits, to));
            return;
          }
        } catch {
          // The hint will say what went wrong.
        }
        if (!stale()) setMode("tick");
      }),
    [api, book, carry],
  );

  // An existing scene opens in dates where its calendar can say them.
  const opened = useRef(false);
  useEffect(() => {
    if (opened.current) return;
    opened.current = true;
    if (lastTicks.current && units.length)
      void showTicksAsDate(lastTicks.current, units, calendarId);
  }, [showTicksAsDate, units, calendarId]);

  // The live hint. Latest wins: a slow answer for an older keystroke must not overwrite a newer one.
  const seq = useRef(0);
  useEffect(() => {
    const mine = ++seq.current;
    const timer = setTimeout(async () => {
      const said = await preview().catch((e: unknown) => ({
        hint: messageOf(e, ""),
        readings: [] as string[],
      }));
      if (mine !== seq.current) return;
      setHint(said.hint);
      setReadings(said.readings);
    }, DEBOUNCE_MS);
    return () => clearTimeout(timer);

    async function preview(): Promise<{ hint: string; readings: string[] }> {
      if (mode === "date") {
        const asked = dateBody(units, startDate, endDate);
        if ("error" in asked) return { hint: asked.error, readings: [] };
        if (!asked.body) return { hint: UNSCHEDULED_HINT, readings: [] };
        const resolved = await api.resolveDates(book, asked.body, { calendar: calendarId });
        lastTicks.current = { start: resolved.start_tick, end: resolved.end_tick };
        return {
          hint: describeDates(resolved, descriptor),
          readings: readingsAt(resolved.ticks, resolved.start_tick),
        };
      }
      const start = intOrNull(startTick);
      const end = intOrNull(endTick);
      if (Number.isNaN(start) || Number.isNaN(end))
        return { hint: "Whole numbers only.", readings: [] };
      if (start === null && end === null) return { hint: UNSCHEDULED_HINT, readings: [] };
      if (start !== null && end !== null) lastTicks.current = { start, end };
      if (!labelsAreUseful(descriptor))
        return { hint: describeTicks([], start, end, descriptor), readings: [] };
      const wanted = [start, end].filter((t): t is number => t !== null);
      const labels = await api.formatTicks(book, wanted, { calendar: calendarId });
      return {
        hint: describeTicks(labels, start, end, descriptor),
        readings: readingsAt(labels, start),
      };
    }
  }, [
    mode,
    startTick,
    endTick,
    startDate,
    endDate,
    calendarId,
    units,
    descriptor,
    api,
    book,
  ]);

  const switchMode = useCallback(
    async (picked: TimingMode) => {
      if (picked === mode) return;
      setMode(picked);
      if (picked === "tick") {
        const asked = dateBody(units, startDate, endDate);
        if ("error" in asked) return;
        if (!asked.body) {
          setStartTick("");
          setEndTick("");
          lastTicks.current = null;
          return;
        }
        const body = asked.body;
        await carry(async (stale) => {
          try {
            const r = await api.resolveDates(book, body, { calendar: calendarId });
            lastTicks.current = { start: r.start_tick, end: r.end_tick };
            // Typed into the tick boxes while the dates were being read: theirs wins.
            if (stale()) return;
            setStartTick(String(r.start_tick));
            setEndTick(String(r.end_tick));
          } catch {
            // The hint will say what went wrong.
          }
        });
        return;
      }
      const asked = tickBody(startTick, endTick);
      if ("error" in asked) return;
      const { start_tick: start, end_tick: end } = asked.body;
      if (start === null || end === null) {
        setStartDate(emptyDate());
        setEndDate(emptyDate());
        lastTicks.current = null;
        return;
      }
      lastTicks.current = { start, end };
      await showTicksAsDate({ start, end }, units, calendarId);
    },
    [
      mode,
      units,
      startDate,
      endDate,
      startTick,
      endTick,
      api,
      book,
      calendarId,
      showTicksAsDate,
      carry,
    ],
  );

  // Nothing about the scene moves: the same ticks, said in another calendar's words.
  const switchCalendar = useCallback(
    (id: string) => {
      const nextUnits = dateUnits(attachmentOf(calendars, id)?.descriptor ?? null);
      setCalendarId(id);
      setStartDate(emptyDate());
      setEndDate(emptyDate());
      if (!nextUnits.length) setMode("tick");
      if (lastTicks.current && (mode === "date" || !nextUnits.length))
        void showTicksAsDate(lastTicks.current, nextUnits, id);
    },
    [calendars, mode, showTicksAsDate],
  );

  const timeframe = useCallback((): Read<TimeframeBody> & { calendar?: string | null } => {
    // Mid-conversion and untouched since: the boxes in view are not filled yet,
    // and reading them would un-schedule the scene. The known ticks are the truth.
    const known = lastTicks.current;
    if (known && carrying.current !== null && carrying.current === edits.current)
      return {
        body: { start_tick: known.start, end_tick: known.end },
        calendar: calendarId,
      };
    const read: Read<TimeframeBody> =
      mode === "date"
        ? withNulls(dateBody(units, startDate, endDate))
        : tickBody(startTick, endTick);
    // Ticks mean the same in every calendar, but the answer is presented through this one, so it rides along.
    return "error" in read ? read : { ...read, calendar: calendarId };
  }, [mode, units, startDate, endDate, startTick, endTick, calendarId]);

  return {
    mode,
    calendars,
    calendarId,
    units,
    startTick,
    endTick,
    startDate,
    endDate,
    hint,
    readings,
    explanation: calendarHint(descriptor),
    setStartTick: typed(setStartTick),
    setEndTick: typed(setEndTick),
    setStartDate: typed(setStartDate),
    setEndDate: typed(setEndDate),
    switchMode: (m) => void switchMode(m),
    switchCalendar,
    timeframe,
  };
}
