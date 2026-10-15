// The manuscript's outline beside the page: every volume and section, a
// filter, and a new chapter at the end of each volume. Following a link waits
// for the autosave, like every way off this page.

import { useState } from "react";
import type { SectionAddress } from "../../api/LogosApi";
import type { Manuscript } from "../../api/types";
import { Icon } from "../../../components/ui/Icon";
import { filterOutline, sectionLabel, sectionName } from "../../logic/outline";

export function OutlinePanel({
  manuscript,
  at,
  hrefFor,
  onOpen,
  onNewChapter,
  onClose,
}: {
  manuscript: Manuscript;
  at: SectionAddress;
  hrefFor: (volume: string, section: string) => string;
  onOpen: (url: string) => void;
  onNewChapter: (volume: string) => void;
  onClose: () => void;
}) {
  const [query, setQuery] = useState("");
  const shown = filterOutline(manuscript, query);
  const filtering = query.trim() !== "";
  return (
    <nav id="lw-outline" className="lw-panel lw-outline" aria-label="Manuscript outline">
      <div className="lw-panel-head">
        <strong>Outline</strong>
        <button
          type="button"
          className="lw-panel-close"
          aria-label="Close outline"
          onClick={onClose}
        >
          <Icon name="x" />
        </button>
      </div>
      <input
        className="lw-outline-search"
        type="search"
        placeholder="Find a chapter"
        aria-label="Filter the outline"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
      />
      <div className="lw-outline-volumes">
        {shown.length ? (
          shown.map((volume) => (
            <section key={volume.id} className="lw-volume">
              <h2>{volume.title}</h2>
              <ol>
                {volume.sections.map((section) => {
                  const url = hrefFor(volume.id, section.id);
                  const current = section.id === at.section && volume.id === at.volume;
                  return (
                    <li key={section.id}>
                      <a
                        href={url}
                        className={current ? "is-current" : undefined}
                        aria-current={current ? "page" : undefined}
                        onClick={(event) => {
                          if (event.metaKey || event.ctrlKey || event.shiftKey) return;
                          event.preventDefault();
                          onOpen(url);
                        }}
                      >
                        <span>{sectionName(section)}</span>
                        {section.title ? <small>{sectionLabel(section)}</small> : null}
                      </a>
                    </li>
                  );
                })}
              </ol>
              {/* A chapter added to a filtered view would land somewhere you cannot see. */}
              {filtering ? null : (
                <button
                  type="button"
                  className="lw-new-chapter"
                  onClick={() => onNewChapter(volume.id)}
                >
                  <Icon name="plus" size={14} /> New chapter
                </button>
              )}
            </section>
          ))
        ) : (
          <p className="lw-muted">No chapter matches that.</p>
        )}
      </div>
    </nav>
  );
}
