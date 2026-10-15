// The small labelled marks the workspace uses everywhere: a goal, a thread,
// an article, a count of problems. Each one that names something opens it.

import type { ReactNode } from "react";
import type { EntityRef, GoalRef } from "../../api/types";
import type { ThreadInfo } from "../../hooks/useThreads";
import { Icon, type IconName } from "../../../components/ui/Icon";
import { EntityName } from "./EntityName";

export function Chip({
  children,
  onClick,
  tone = "neutral",
  icon,
  title,
  className = "",
}: {
  children: ReactNode;
  onClick?: () => void;
  tone?: "neutral" | "ok" | "warn" | "danger" | "accent" | "muted";
  icon?: IconName;
  title?: string;
  className?: string;
}) {
  const classes = `cw-chip cw-chip-${tone} ${className}`.trim();
  const body = (
    <>
      {icon ? <Icon name={icon} size={12} /> : null}
      <span className="cw-chip-text">{children}</span>
    </>
  );
  return onClick ? (
    <button type="button" className={classes} onClick={onClick} title={title}>
      {body}
    </button>
  ) : (
    <span className={classes} title={title}>
      {body}
    </span>
  );
}

/** "✓ achieved", "○ open" or "missing": what a goal's state reads as on a chip. */
export function goalTone(goal: Pick<GoalRef, "achieved" | "missing">) {
  if (goal.missing) return "danger" as const;
  return goal.achieved ? ("ok" as const) : ("muted" as const);
}

export function GoalChip({
  goal,
  onOpen,
}: {
  goal: GoalRef;
  onOpen?: (id: string) => void;
}) {
  const state = goal.missing ? "missing" : goal.achieved ? "achieved" : "open";
  return (
    <Chip
      tone={goalTone(goal)}
      icon={goal.achieved ? "check" : "target"}
      onClick={onOpen ? () => onOpen(goal.id) : undefined}
      title={`Goal (${state})${goal.achieved_scene ? ` at ${goal.achieved_scene.title}` : ""}`}
    >
      {goal.title}
    </Chip>
  );
}

export function ThreadDot({ thread, size = 10 }: { thread?: ThreadInfo; size?: number }) {
  return (
    <span
      className={`cw-thread-dot${thread?.turn ? ` is-turn-${thread.turn}` : ""}`}
      style={{ width: size, height: size, background: thread?.color ?? "var(--muted)" }}
      aria-hidden="true"
    />
  );
}

export function ThreadChip({
  thread,
  id,
  onOpen,
}: {
  thread?: ThreadInfo;
  id: string;
  onOpen?: (id: string) => void;
}) {
  const classes = "cw-chip cw-chip-thread";
  const body = (
    <>
      <ThreadDot thread={thread} size={8} />
      <span className="cw-chip-text">{thread?.title ?? id}</span>
    </>
  );
  return onOpen ? (
    <button
      type="button"
      className={classes}
      onClick={() => onOpen(id)}
      title="Open this thread"
    >
      {body}
    </button>
  ) : (
    <span className={classes}>{body}</span>
  );
}

const COLLECTION_ICONS: Record<string, IconName> = {
  characters: "user",
  locations: "pin",
  items: "gem",
};

export function collectionIcon(collection: string): IconName {
  return COLLECTION_ICONS[collection] ?? "book";
}

export function ArticleChip({
  book,
  entity,
  onOpen,
}: {
  book: string;
  entity: EntityRef;
  onOpen?: (ref: EntityRef) => void;
}) {
  return (
    <Chip
      tone="accent"
      icon={collectionIcon(entity.collection)}
      onClick={onOpen ? () => onOpen(entity) : undefined}
      title={`${entity.collection} · ${entity.id}`}
    >
      <EntityName book={book} entity={entity} />
    </Chip>
  );
}

/** "3 problems" in the attention colour, or a quiet dash when there are none. */
export function ProblemCount({
  count,
  noun = "problem",
}: {
  count: number;
  noun?: string;
}) {
  if (!count) return <span className="cw-quiet">—</span>;
  return (
    <span className="cw-problems">
      {count} {noun}
      {count === 1 ? "" : "s"}
    </span>
  );
}
