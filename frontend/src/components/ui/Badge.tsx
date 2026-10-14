import type { ReactNode } from "react";

export type BadgeTone = "neutral" | "accent" | "ok" | "warn" | "danger";

export function Badge({
  tone = "neutral",
  children,
  title,
}: {
  tone?: BadgeTone;
  children: ReactNode;
  title?: string;
}) {
  return (
    <span className={`st-badge st-badge-${tone}`} title={title}>
      {children}
    </span>
  );
}
