// Focus mode: hide the continuity marks so a thread can be arranged in peace.
//
// It hides, it never silences: nothing stops being computed and a save behaves
// the same; only the marks are out of sight. And the button always says what
// it is hiding, so a writer who leaves it on cannot mistake a quiet screen for
// a sound story. Remembered under the classic page's own key.

export const FOCUS_KEY = "chronos-focus";

export const isHidden = (stored: string | null) => stored === "1";

export function focusLabel(hidden: boolean, conflicts: number): string {
  if (!hidden) return "Hide problems";
  if (conflicts) return `Show ${conflicts} problem${conflicts === 1 ? "" : "s"}`;
  return "Show notes";
}
