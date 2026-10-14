export type DotTone = "ok" | "warn" | "off" | "accent" | "danger" | "muted";

/** A coloured dot; `pulse` for something happening right now. */
export function StatusDot({ tone, pulse = false }: { tone: DotTone; pulse?: boolean }) {
  return (
    <span
      className={`st-dot st-dot-${tone}${pulse ? " is-pulsing" : ""}`}
      aria-hidden="true"
    />
  );
}
