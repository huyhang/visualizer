import type { ReactNode } from "react";
import { Icon, type IconName } from "./ui/Icon";

export type PaneName = "topics" | "draft" | "note";

const TABS: { name: PaneName; icon: IconName; label: string }[] = [
  { name: "topics", icon: "layers", label: "Topics" },
  { name: "draft", icon: "book", label: "Draft" },
  { name: "note", icon: "note", label: "Note" },
];

/**
 * Three panes side by side on a wide screen; on a narrow one, one pane at a
 * time behind a segmented switch, with the note's size on its tab so material
 * added from the draft is visibly going somewhere.
 */
export function StudioLayout({
  narrow,
  pane,
  onPane,
  noteCount,
  draftLabel,
  topics,
  draft,
  note,
}: {
  narrow: boolean;
  pane: PaneName;
  onPane: (pane: PaneName) => void;
  noteCount: number;
  draftLabel: string;
  topics: ReactNode;
  draft: ReactNode;
  note: ReactNode;
}) {
  if (!narrow) {
    return (
      <div className="st-studio is-wide">
        {topics}
        {draft}
        {note}
      </div>
    );
  }
  const panes = { topics, draft, note };
  return (
    <div className="st-studio is-narrow">
      <nav className="st-pane-switch" aria-label="Studio panes">
        {TABS.map((tab) => (
          <button
            key={tab.name}
            type="button"
            className={pane === tab.name ? "is-on" : ""}
            aria-pressed={pane === tab.name}
            onClick={() => onPane(tab.name)}
          >
            <Icon name={tab.icon} size={15} />
            <span className="st-ellipsis">
              {tab.name === "draft" ? draftLabel : tab.label}
            </span>
            {tab.name === "note" && noteCount ? (
              <span key={noteCount} className="st-count is-bump">
                {noteCount}
              </span>
            ) : null}
          </button>
        ))}
      </nav>
      {panes[pane]}
    </div>
  );
}
