import type { ReactNode } from "react";
import type { TopicNode } from "../../logic/topics";
import { timeAgo } from "../../logic/format";
import { Icon } from "../ui/Icon";

/** Where this topic sits in its line of inquiry, its question, and what can be done. */
export function TopicHeader({
  topic,
  path,
  title,
  onSelect,
  badges,
  actions,
}: {
  topic: TopicNode;
  path: TopicNode[];
  title: string;
  onSelect: (id: string) => void;
  badges?: ReactNode;
  actions?: ReactNode;
}) {
  const ancestors = path.slice(0, -1);
  const showQuestion = topic.job.question.trim() !== title.trim();
  return (
    <header className="st-topic-head">
      {ancestors.length ? (
        <nav className="st-topic-path" aria-label="Topic path">
          {ancestors.map((node) => (
            <button key={node.job.id} type="button" onClick={() => onSelect(node.job.id)}>
              {node.title}
              <Icon name="chevronRight" size={12} />
            </button>
          ))}
        </nav>
      ) : null}
      <h1 className="st-topic-heading">{title}</h1>
      {showQuestion ? <p className="st-topic-question">“{topic.job.question}”</p> : null}
      <div className="st-topic-meta">
        <span>
          Asked by {topic.job.requester} · {timeAgo(topic.job.created_at)}
        </span>
        {badges}
      </div>
      {actions ? <div className="st-topic-actions">{actions}</div> : null}
    </header>
  );
}
