// The GPU box's state, as a pill: a tone and a word or two.

import type { Availability, AvailabilityState } from "../api/types";

export type Tone = "ok" | "warn" | "off";

const LABELS: Record<AvailabilityState, string> = {
  ready: "Ready",
  cold: "Warming up",
  busy: "Busy",
  queue_full: "Queue full",
  degraded: "Degraded",
  unreachable: "Asleep",
  misconfigured: "Misconfigured",
  incompatible: "Incompatible",
  off: "Off",
};

const TONES: Record<AvailabilityState, Tone> = {
  ready: "ok",
  cold: "ok",
  busy: "warn",
  queue_full: "warn",
  degraded: "warn",
  unreachable: "off",
  misconfigured: "off",
  incompatible: "off",
  off: "off",
};

export function boxLabel(state: AvailabilityState): string {
  return LABELS[state];
}

export function boxTone(state: AvailabilityState): Tone {
  return TONES[state];
}

/** What the second-check line under the pill says. */
export function verifierLine(availability: Availability): string {
  if (availability.verifier === "up") return "Facts will be second-checked.";
  if (availability.verifier === "down")
    return "The second checker is down: first pass only.";
  return "No second checker: first pass only.";
}
