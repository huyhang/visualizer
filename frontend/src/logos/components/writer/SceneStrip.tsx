// The scenes this section tells, above its title: when, where and who, from
// Chronos and Akasha. Swipe, scroll or step either way to the scenes the
// sections around it tell; the strip opens on this section's own.

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useLayoutEffect, useMemo, useRef, useState } from "react";
import type { SectionAddress } from "../../api/LogosApi";
import { messageOf } from "../../api/errors";
import type { SceneArticle, SectionSummary } from "../../api/types";
import { Icon } from "../../../components/ui/Icon";
import { useDeps } from "../../deps";
import { sectionLabel, sectionName } from "../../logic/outline";
import { sceneIds, sceneTrack, type StripCard } from "../../logic/scenes";
import { SceneDialog } from "./SceneDialog";

export function SceneStrip({
  at,
  sections,
  onSave,
  onOpenArticle,
  onOpenSection,
}: {
  at: SectionAddress;
  /** The volume's sections, in order. */
  sections: SectionSummary[];
  /** Save which scenes this section tells; false if the words could not be saved first. */
  onSave: (eventIds: string[]) => Promise<boolean>;
  onOpenArticle: (ref: SceneArticle) => void;
  onOpenSection: (section: SectionSummary) => void;
}) {
  const { api, preferences } = useDeps();
  const client = useQueryClient();
  const key = ["scene-cards", at.book, at.volume];
  const cards = useQuery({
    queryKey: key,
    queryFn: () => api.sceneCards(at.book, at.volume),
  });
  const [open, setOpenState] = useState(() => preferences.scenesOpen());
  const [choosing, setChoosing] = useState(false);
  const track = useMemo(
    () => (cards.data ? sceneTrack(cards.data, sections, at.section) : null),
    [cards.data, sections, at.section],
  );
  const [shown, setShown] = useState(0);
  const rail = useRef<HTMLDivElement>(null);

  const setOpen = (next: boolean) => {
    preferences.setScenesOpen(next);
    setOpenState(next);
  };

  const scrollTo = (index: number, behavior: ScrollBehavior) => {
    const box = rail.current;
    const card = box?.children[index] as HTMLElement | undefined;
    if (!box || !card) return;
    // jsdom has no layout to scroll; the count and buttons follow `shown`.
    box.scrollTo?.({
      left: card.offsetLeft - (box.clientWidth - card.offsetWidth) / 2,
      behavior,
    });
  };

  const go = (index: number) => {
    setShown(index);
    const still = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    scrollTo(index, still ? "instant" : "smooth");
  };

  // Arrive, and come back after a save, at this section's own scenes.
  const start = track?.start ?? 0;
  const count = track?.cards.length ?? 0;
  useLayoutEffect(() => {
    if (!open || !count) return;
    setShown(start);
    scrollTo(start, "instant");
  }, [open, start, count]);

  /** Whichever card is nearest the middle, as the rail is scrolled by hand. */
  const followScroll = () => {
    const box = rail.current;
    if (!box) return;
    const middle = box.scrollLeft + box.clientWidth / 2;
    let nearest = 0;
    let distance = Infinity;
    Array.from(box.children as HTMLCollectionOf<HTMLElement>).forEach((card, i) => {
      const off = Math.abs(card.offsetLeft + card.offsetWidth / 2 - middle);
      if (off < distance) [nearest, distance] = [i, off];
    });
    setShown(nearest);
  };

  if (cards.isLoading) return null;
  if (cards.isError) {
    return (
      <section className="lw-scenes" aria-label="Scenes">
        <p className="lw-muted lw-small">
          {messageOf(cards.error, "The scenes for this volume could not be loaded.")}
        </p>
      </section>
    );
  }
  if (!track) return null;

  const here = track.cards[track.start];
  const current = cards.data ? sceneIds(cards.data, at.section) : [];
  const section = sections.find((s) => s.id === at.section);
  const visible = track.cards[shown] ?? here;

  return (
    <section className={`lw-scenes${open ? "" : " is-closed"}`} aria-label="Scenes">
      <div className="lw-scenes-head">
        <button
          type="button"
          className="lw-scenes-toggle"
          aria-expanded={open}
          onClick={() => setOpen(!open)}
        >
          <Icon name="chevronDown" size={14} />
          <span className="lw-scenes-label">Scenes</span>
          {!open ? (
            <span className="lw-scenes-summary">
              {here?.scene
                ? `${here.scene.title}${here.scene.when ? ` · ${here.scene.when}` : ""}`
                : "None linked"}
              {here && here.of > 1 ? ` +${here.of - 1}` : ""}
            </span>
          ) : null}
        </button>
        {open && count > 1 ? (
          <div className="lw-scenes-nav">
            <button
              type="button"
              className="st-icon-btn lw-scenes-step is-back"
              aria-label="Previous scene"
              disabled={shown <= 0}
              onClick={() => go(shown - 1)}
            >
              <Icon name="chevronRight" size={16} />
            </button>
            <span className="lw-scenes-count" aria-live="polite">
              {shown + 1} of {count}
            </span>
            <button
              type="button"
              className="st-icon-btn lw-scenes-step"
              aria-label="Next scene"
              disabled={shown >= count - 1}
              onClick={() => go(shown + 1)}
            >
              <Icon name="chevronRight" size={16} />
            </button>
          </div>
        ) : null}
      </div>
      {open ? (
        <div
          ref={rail}
          className="lw-scenes-rail"
          tabIndex={0}
          role="group"
          aria-roledescription="carousel"
          aria-label={visible ? describe(visible) : "Scenes"}
          onScroll={followScroll}
        >
          {track.cards.map((card, i) => (
            <SceneCard
              key={card.key}
              card={card}
              current={i === shown}
              onChoose={() => setChoosing(true)}
              onOpenArticle={onOpenArticle}
              onOpenSection={onOpenSection}
            />
          ))}
        </div>
      ) : null}
      {choosing ? (
        <SceneDialog
          book={at.book}
          name={section ? sectionName(section) : "this section"}
          current={current}
          onSave={async (ids) => {
            if (!(await onSave(ids)))
              throw new Error("Your words could not be saved, so the scenes were not.");
            await client.invalidateQueries({ queryKey: key });
          }}
          onClose={() => setChoosing(false)}
        />
      ) : null}
    </section>
  );
}

/** Where a card's section sits: this one, or the one it names. */
function describe(card: StripCard): string {
  const where =
    card.side === "here" ? `This ${card.section.kind}` : sectionLabel(card.section);
  return card.of > 1 ? `${where} · scene ${card.index} of ${card.of}` : where;
}

function SceneCard({
  card,
  current,
  onChoose,
  onOpenArticle,
  onOpenSection,
}: {
  card: StripCard;
  current: boolean;
  onChoose: () => void;
  onOpenArticle: (ref: SceneArticle) => void;
  onOpenSection: (section: SectionSummary) => void;
}) {
  const { scene, section, side } = card;
  const here = side === "here";
  // Only the card in view takes Tab, so the rail is not a run of hidden stops.
  const focus = current ? undefined : -1;
  const article = (ref: SceneArticle, className: string) => (
    <button
      type="button"
      className={className}
      tabIndex={focus}
      title={`Open ${ref.title} in Akasha`}
      onClick={() => onOpenArticle(ref)}
    >
      {ref.title}
    </button>
  );

  return (
    <article
      className={`lw-scene lw-scene-${side}${scene?.missing ? " is-missing" : ""}`}
      aria-hidden={current ? undefined : true}
    >
      <p className="lw-scene-where">
        {here ? (
          <span>{describe(card)}</span>
        ) : (
          <button
            type="button"
            className="lw-scene-section"
            tabIndex={focus}
            title={`Write ${sectionName(section)}`}
            onClick={() => onOpenSection(section)}
          >
            {describe(card)}
            {section.title ? <span className="lw-muted"> · {section.title}</span> : null}
          </button>
        )}
        {here ? (
          <button
            type="button"
            className="lw-scene-change"
            tabIndex={focus}
            onClick={onChoose}
          >
            {scene ? "Change scenes" : "Link scenes"}
          </button>
        ) : null}
      </p>
      {!scene ? (
        <p className="lw-scene-empty">
          No Chronos scene is linked to this {section.kind} yet. Link the ones it tells to
          keep their when, where and who in view as you write.
        </p>
      ) : scene.missing ? (
        <>
          <p className="lw-scene-title">{scene.title}</p>
          <p className="lw-scene-meta">This scene is no longer in Chronos.</p>
        </>
      ) : (
        <>
          <p className="lw-scene-title">{scene.title}</p>
          <p className="lw-scene-meta">
            <span>{scene.when}</span>
            {scene.place ? (
              <>
                <span aria-hidden="true"> · </span>
                {article(scene.place, "lw-scene-place")}
              </>
            ) : null}
          </p>
          {scene.description ? (
            <p className="lw-scene-description">{scene.description}</p>
          ) : null}
          {scene.cast.length || scene.unseen ? (
            <p className="lw-scene-cast">
              {scene.cast.map((person) => (
                <span key={`${person.database}/${person.collection}/${person.id}`}>
                  {article(person, "lw-scene-person")}
                </span>
              ))}
              {scene.unseen ? (
                <span className="lw-muted lw-small">
                  {scene.cast.length ? "+" : ""}
                  {scene.unseen} you can't open
                </span>
              ) : null}
            </p>
          ) : null}
        </>
      )}
    </article>
  );
}
