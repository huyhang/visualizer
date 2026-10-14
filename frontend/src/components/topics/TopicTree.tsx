import { useState } from "react";
import type { TopicNode, TopicStatus } from "../../logic/topics";
import { Icon } from "../ui/Icon";
import { StatusDot, type DotTone } from "../ui/StatusDot";

const STATUS: Record<TopicStatus, { tone: DotTone; label: string; pulse?: boolean }> = {
  researching: { tone: "accent", label: "Researching", pulse: true },
  "needs-approval": { tone: "warn", label: "Needs your OK" },
  ready: { tone: "ok", label: "Ready to read" },
  failed: { tone: "danger", label: "Failed" },
  saved: { tone: "muted", label: "Saved to notes" },
  closed: { tone: "muted", label: "Closed" },
};

/** A topic's dot: its own state, unless a steer of its draft is under way. */
function statusOf(node: TopicNode): (typeof STATUS)[TopicStatus] {
  const steer = node.refinement;
  if (steer?.state === "awaiting_approval") {
    return { tone: "warn", label: "Steer needs your OK" };
  }
  if (steer && steer.state !== "failed") {
    return { tone: "accent", label: "Being steered", pulse: true };
  }
  return STATUS[node.status];
}

/** The world's lines of inquiry: each question, and what was dug out of it. */
export function TopicTree({
  nodes,
  selectedId,
  onSelect,
}: {
  nodes: TopicNode[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  return (
    <ul className="st-tree" role="tree" aria-label="Research topics">
      {nodes.map((node) => (
        <TopicItem
          key={node.job.id}
          node={node}
          depth={0}
          selectedId={selectedId}
          onSelect={onSelect}
        />
      ))}
    </ul>
  );
}

function TopicItem({
  node,
  depth,
  selectedId,
  onSelect,
}: {
  node: TopicNode;
  depth: number;
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const [open, setOpen] = useState(true);
  const status = statusOf(node);
  const selected = node.job.id === selectedId;
  const hasChildren = node.children.length > 0;

  return (
    <li
      role="treeitem"
      aria-selected={selected}
      aria-expanded={hasChildren ? open : undefined}
    >
      <div
        className={`st-topic${selected ? " is-selected" : ""} is-${node.status}`}
        style={{ paddingLeft: `${0.5 + depth * 0.95}rem` }}
      >
        {hasChildren ? (
          <button
            type="button"
            className="st-twisty"
            aria-label={open ? "Fold" : "Unfold"}
            onClick={() => setOpen(!open)}
          >
            <Icon name={open ? "chevronDown" : "chevronRight"} size={14} />
          </button>
        ) : (
          <span className="st-twisty-gap" />
        )}
        <button
          type="button"
          className="st-topic-main"
          onClick={() => onSelect(node.job.id)}
          title={node.job.question}
        >
          <StatusDot tone={status.tone} pulse={status.pulse} />
          <span className="st-topic-title">{node.title}</span>
          <span className="st-sr-only">, {status.label}</span>
          {node.job.notes.length ? (
            <span className="st-topic-notes" title={`In ${node.job.notes.length} note(s)`}>
              <Icon name="note" size={12} />
              {node.job.notes.length}
            </span>
          ) : null}
        </button>
      </div>
      {hasChildren && open ? (
        <ul role="group">
          {node.children.map((child) => (
            <TopicItem
              key={child.job.id}
              node={child}
              depth={depth + 1}
              selectedId={selectedId}
              onSelect={onSelect}
            />
          ))}
        </ul>
      ) : null}
    </li>
  );
}
