// The bar over the writing page: where you are, which draft, what you can do
// to it, how many words, whether they are saved, and the way out.

import type { SaveStatus as Status } from "../../hooks/useDraftSession";
import type { DraftState } from "../../logic/drafts";
import { draftCapabilities, draftOptions } from "../../logic/drafts";
import { Action } from "../ui/Action";
import { SaveStatus } from "./SaveStatus";

export interface TopBarActions {
  back: () => void;
  switchDraft: (id: string) => void;
  newDraft: () => void;
  rename: () => void;
  makePrimary: () => void;
  compare: () => void;
  preserve: () => void;
  toggleOutline: () => void;
  toggleTools: () => void;
  done: () => void;
}

export function TopBar({
  where,
  backHref,
  drafts,
  words,
  status,
  openDrawer,
  toolsCount,
  actions,
}: {
  where: string;
  backHref: string;
  drafts: DraftState;
  words: number;
  status: Status;
  openDrawer: "outline" | "tools" | null;
  toolsCount: number;
  actions: TopBarActions;
}) {
  const can = draftCapabilities(drafts.rows.length, drafts.current.primary);
  return (
    <header className="lw-topbar">
      <button
        type="button"
        className="lw-drawer-button lw-outline-button"
        aria-label="Open outline"
        aria-controls="lw-outline"
        aria-expanded={openDrawer === "outline"}
        title="Outline"
        onClick={actions.toggleOutline}
      >
        <span aria-hidden="true" className="lw-glyph">
          ☰
        </span>
      </button>
      <a
        className="lw-back"
        href={backHref}
        onClick={(event) => {
          if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0)
            return;
          event.preventDefault();
          actions.back();
        }}
      >
        {where}
      </a>
      {can.canSwitch ? (
        <select
          className="lw-draft-select"
          aria-label="Current draft"
          value={drafts.current.id}
          onChange={(event) => actions.switchDraft(event.target.value)}
        >
          {draftOptions(drafts).map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      ) : null}
      {can.showPrimaryBadge ? <span className="lw-primary-badge">Primary</span> : null}
      <div className="lw-topbar-row">
        <div className="lw-draft-actions">
          <Action icon="plus" label="New draft" onClick={actions.newDraft} />
          <Action icon="rename" label="Rename" onClick={actions.rename} />
          {can.canPromote ? (
            <Action icon="star" label="Make primary" onClick={actions.makePrimary} />
          ) : null}
          {can.canCompare ? (
            <Action icon="compare" label="Compare" onClick={actions.compare} />
          ) : null}
        </div>
        <span className="lw-words">{words.toLocaleString()} words</span>
        <SaveStatus status={status} />
        {status.state === "conflict" ? (
          <Action
            icon="arrowUp"
            label="Preserve as new draft"
            tone="accent"
            onClick={actions.preserve}
          />
        ) : null}
      </div>
      <button
        type="button"
        className="lw-drawer-button lw-tools-button"
        aria-label="Open writing tools"
        aria-controls="lw-tools"
        aria-expanded={openDrawer === "tools"}
        title="Writing tools"
        onClick={actions.toggleTools}
      >
        <span aria-hidden="true" className="lw-glyph">
          ✦
        </span>
        {toolsCount ? (
          <span className="lw-drawer-count">{toolsCount > 99 ? "99+" : toolsCount}</span>
        ) : null}
      </button>
      <Action
        icon="check"
        label="Done"
        tone="primary"
        className="lw-done"
        onClick={actions.done}
      />
    </header>
  );
}
