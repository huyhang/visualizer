// The character lens, workspace-wide: the sidebar picks who to follow, and
// every screen that shows scenes asks `useLens()` which of them to light up.
// It belongs to the book -- leaving the book puts it down.

import { createContext, useContext, useMemo, useState, type ReactNode } from "react";
import type { EntityRef } from "../../api/types";
import { useEntity, useSceneListing } from "../../hooks/queries";
import {
  castIndex,
  castList,
  refKey,
  scenesFeaturing,
  type CastMember,
} from "../../logic/lens";
import { plural } from "../../logic/text";
import { collectionIcon } from "../common/Chips";
import { EntityName, entityTitle } from "../common/EntityName";
import { useOptionalBookScope } from "./BookScope";
import { Icon } from "../../../components/ui/Icon";
import { IconButton } from "../../../components/ui/Button";

export interface Lens {
  /** Who is being followed, or null when nobody is. */
  subject: EntityRef | null;
  follow: (ref: EntityRef | null) => void;
  /** The scenes the subject is in; null when nobody is followed. */
  featured: Set<string> | null;
  /** Whether a scene should fade: someone is followed and is not in it. */
  fades: (scene: string) => boolean;
  cast: CastMember[];
}

const NO_LENS: Lens = {
  subject: null,
  follow: () => {},
  featured: null,
  fades: () => false,
  cast: [],
};

const LensContext = createContext<Lens>(NO_LENS);

/** Who is in each scene of the book, from its one scene listing. */
function useCastIndex(book: string, calendar: string | null) {
  const { data: scenes } = useSceneListing(book, calendar);
  return useMemo(() => castIndex(scenes ?? []), [scenes]);
}

function BookLens({
  book,
  calendar,
  children,
}: {
  book: string;
  calendar: string | null;
  children: ReactNode;
}) {
  const [subject, setSubject] = useState<EntityRef | null>(null);
  const index = useCastIndex(book, calendar);
  const lens = useMemo<Lens>(() => {
    const featured = subject ? scenesFeaturing(index, subject) : null;
    return {
      subject,
      follow: setSubject,
      featured,
      fades: (scene) => featured !== null && !featured.has(scene),
      cast: castList(index),
    };
  }, [subject, index]);
  return <LensContext.Provider value={lens}>{children}</LensContext.Provider>;
}

export function LensProvider({ children }: { children: ReactNode }) {
  const scope = useOptionalBookScope();
  if (!scope) return <>{children}</>;
  return (
    <BookLens book={scope.id} calendar={scope.calendar} key={scope.id}>
      {children}
    </BookLens>
  );
}

export function useLens(): Lens {
  return useContext(LensContext);
}

/** The sidebar's control: who to follow, and how many scenes they are in. */
export function LensPicker() {
  const scope = useOptionalBookScope();
  const lens = useLens();
  if (!scope || lens.cast.length === 0) return null;
  const chosen = lens.subject ? refKey(lens.subject) : "";
  const subject = lens.subject;
  return (
    <div className="cw-lens">
      <label className="cw-calendar-switch-label" htmlFor="cw-lens-pick">
        <Icon name="lens" size={14} /> Follow
      </label>
      {subject ? (
        <div className="cw-lens-on">
          <Icon name={collectionIcon(subject.collection)} size={14} />
          <span className="cw-lens-name">
            <EntityName book={scope.id} entity={subject} />
          </span>
          <span className="cw-lens-count">{lens.featured?.size ?? 0}</span>
          <IconButton icon="x" label="Stop following" onClick={() => lens.follow(null)} />
        </div>
      ) : (
        <select
          id="cw-lens-pick"
          className="st-input st-input-sm"
          value={chosen}
          aria-label="Follow a character, place or thing"
          onChange={(e) =>
            lens.follow(
              lens.cast.find((m) => refKey(m.ref) === e.target.value)?.ref ?? null,
            )
          }
        >
          <option value="">Nobody</option>
          {lens.cast.map((m) => (
            <CastOption key={refKey(m.ref)} book={scope.id} member={m} />
          ))}
        </select>
      )}
    </div>
  );
}

function CastOption({ book, member }: { book: string; member: CastMember }) {
  const { data } = useEntity(book, member.ref);
  // An <option> holds text only, so the title is read here rather than through EntityName.
  const name = entityTitle(data?.document, member.ref.id);
  return (
    <option
      value={refKey(member.ref)}
    >{`${name} · ${plural(member.scenes, "scene")}`}</option>
  );
}

/**
 * Who is being followed, said where the screens begin, with the way to stop:
 * on a phone the picker is tucked into the View sheet, and faded scenes need
 * a reason in sight.
 */
export function LensChip() {
  const scope = useOptionalBookScope();
  const lens = useLens();
  if (!scope || !lens.subject) return null;
  return (
    <div className="cw-lens-chip" role="status">
      <Icon name="lens" size={14} />
      <span className="cw-lens-chip-text">
        Following <EntityName book={scope.id} entity={lens.subject} /> ·{" "}
        {plural(lens.featured?.size ?? 0, "scene")}
      </span>
      <IconButton icon="x" label="Stop following" onClick={() => lens.follow(null)} />
    </div>
  );
}
