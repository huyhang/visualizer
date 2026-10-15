// The writing tools beside the page: Akasha, the Coach and the Editor, as tabs.

import { Tabs } from "radix-ui";
import type { ReactNode } from "react";
import { Icon } from "../../../components/ui/Icon";
import type { Panel } from "../../logic/route";

export function ToolsPanel({
  tab,
  onTab,
  onClose,
  counts,
  akasha,
  coach,
  editor,
}: {
  tab: Panel;
  onTab: (tab: Panel) => void;
  onClose: () => void;
  counts: { coach: number; editor: number };
  akasha: ReactNode;
  coach: ReactNode;
  editor: ReactNode;
}) {
  const count = (n: number, what: string) =>
    n ? (
      <span className="lw-tab-count" aria-label={`${n} ${what}`}>
        {n > 99 ? "99+" : n}
      </span>
    ) : null;
  return (
    <aside id="lw-tools" className="lw-panel lw-tools" aria-label="Writing tools">
      <Tabs.Root
        value={tab}
        onValueChange={(value) => onTab(value as Panel)}
        className="lw-tabs-root"
      >
        <div className="lw-panel-head">
          <Tabs.List className="lw-tabs" aria-label="Writing tools">
            <Tabs.Trigger value="akasha" className="lw-tab">
              Akasha
            </Tabs.Trigger>
            <Tabs.Trigger value="coach" className="lw-tab">
              Coach {count(counts.coach, "suggestions")}
            </Tabs.Trigger>
            <Tabs.Trigger value="editor" className="lw-tab">
              Editor {count(counts.editor, "open issues")}
            </Tabs.Trigger>
          </Tabs.List>
          <button
            type="button"
            className="lw-panel-close"
            aria-label="Close writing tools"
            onClick={onClose}
          >
            <Icon name="x" />
          </button>
        </div>
        <Tabs.Content value="akasha" className="lw-tab-body">
          {akasha}
        </Tabs.Content>
        <Tabs.Content value="coach" className="lw-tab-body">
          {coach}
        </Tabs.Content>
        <Tabs.Content value="editor" className="lw-tab-body">
          {editor}
        </Tabs.Content>
      </Tabs.Root>
    </aside>
  );
}
