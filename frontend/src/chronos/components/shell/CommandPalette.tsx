// ⌘K: jump to any thread, scene, goal or book, or start something new.
//
// Inside a book everything comes from the story graph and the cast the rest
// of the workspace already holds, so opening the palette costs no request.

import { Dialog } from "radix-ui";
import { useEffect, useState, type KeyboardEvent } from "react";
import { useQueries } from "@tanstack/react-query";
import type { EntityRef, Graph } from "../../api/types";
import { useApi } from "../../deps";
import { keys, useBooks, useGraph } from "../../hooks/queries";
import { useRoute } from "../../hooks/useRoute";
import type { InspectorTarget } from "../../logic/inspector";
import { bookOf, to, type Route } from "../../logic/route";
import { refKey } from "../../logic/lens";
import { rank } from "../../logic/search";
import { plural } from "../../logic/text";
import { collectionIcon } from "../common/Chips";
import { entityTitle } from "../common/EntityName";
import { useActions, type WorkspaceActions } from "./Actions";
import { useInspector } from "./InspectorContext";
import { useLens } from "./Lens";
import { Icon, type IconName } from "../../../components/ui/Icon";

export interface PaletteItem {
  key: string;
  label: string;
  hint: string;
  icon: IconName;
  run: () => void;
}

interface Sinks {
  go: (route: Route) => void;
  inspect: (target: InspectorTarget) => void;
  actions: WorkspaceActions;
}

function bookPlaces(book: string, sinks: Sinks): PaletteItem[] {
  const place = (
    key: string,
    label: string,
    icon: IconName,
    route: Route,
  ): PaletteItem => ({
    key: `go:${key}`,
    label,
    hint: "Go to",
    icon,
    run: () => sinks.go(route),
  });
  return [
    place("threads", "Threads", "branch", to.threads(book)),
    place("scenes", "Scenes", "scenes", to.scenes(book)),
    place("goals", "Goals", "target", to.goals(book)),
    place("map", "Story map", "map", to.map(book)),
    place("issues", "Issues", "alert", to.issues(book)),
  ];
}

function creations(actions: WorkspaceActions): PaletteItem[] {
  const offers: [keyof WorkspaceActions, string][] = [
    ["newThread", "New thread"],
    ["newScene", "New scene"],
    ["newGoal", "New goal"],
    ["newBook", "New book"],
  ];
  return offers.flatMap(([name, label]) => {
    const run = actions[name] as (() => void) | undefined;
    return run
      ? [{ key: `new:${name}`, label, hint: "Create", icon: "plus" as IconName, run }]
      : [];
  });
}

/** Everything in the book worth jumping to, from its story graph. */
export function graphItems(
  book: string,
  graph: Graph | undefined,
  sinks: Sinks,
): PaletteItem[] {
  if (!graph) return [];
  const threads = graph.plotlines.map((p) => ({
    key: `thread:${p.id}`,
    label: p.title || p.id,
    hint: "Thread",
    icon: "branch" as IconName,
    run: () => sinks.go(to.plotline(book, p.id)),
  }));
  const scenes = graph.nodes.map((n) => ({
    key: `scene:${n.id}`,
    label: n.title || n.id,
    hint: n.start_label ? `Scene · ${n.start_label}` : "Scene",
    icon: "scenes" as IconName,
    run: () => sinks.inspect({ kind: "scene", id: n.id }),
  }));
  const goals = (graph.goals ?? []).map((g) => ({
    key: `goal:${g.id}`,
    label: g.title,
    hint: "Goal",
    icon: "target" as IconName,
    run: () => sinks.go(to.goals(book, g.id)),
  }));
  return [...threads, ...scenes, ...goals];
}

/** Who appears in the book: open their article beside the page, or follow them. */
export function castItems(
  cast: { ref: EntityRef; scenes: number; title: string }[],
  sinks: Sinks & { follow: (ref: EntityRef) => void },
): PaletteItem[] {
  return cast.flatMap(({ ref, scenes, title }) => [
    {
      key: `article:${refKey(ref)}`,
      label: title,
      hint: `${ref.collection} · ${plural(scenes, "scene")}`,
      icon: collectionIcon(ref.collection),
      run: () => sinks.inspect({ kind: "article", ref }),
    },
    {
      key: `follow:${refKey(ref)}`,
      label: `Follow ${title}`,
      hint: "Fade every scene they are not in",
      icon: "lens" as IconName,
      run: () => sinks.follow(ref),
    },
  ]);
}

/** The cast with their titles, read from the articles the lens has already fetched. */
function useNamedCast(book: string | null) {
  const api = useApi();
  const { cast } = useLens();
  const titles = useQueries({
    queries: cast.map(({ ref }) => ({
      queryKey: keys.entity(book ?? "", ref.database, ref.collection, ref.id),
      queryFn: () => api.getEntity(book ?? "", ref.database, ref.collection, ref.id),
      enabled: book !== null,
      staleTime: 5 * 60_000,
    })),
  });
  return cast.map((member, n) => ({
    ...member,
    title: entityTitle(titles[n]?.data?.document, member.ref.id),
  }));
}

function usePaletteItems(): PaletteItem[] {
  const { route, go } = useRoute();
  const inspector = useInspector();
  const actions = useActions();
  const book = bookOf(route);
  const { data: books } = useBooks();
  const { data: graph } = useGraph(book, null);
  const { follow } = useLens();
  const cast = useNamedCast(book);
  // Rebuilt on each render rather than memoised: a few hundred plain objects,
  // and only while the palette is open (see PaletteBody).
  const sinks: Sinks = { go, inspect: inspector.open, actions };
  const bookItems = (books ?? []).map((b) => ({
    key: `book:${b.id}`,
    label: b.title || b.id,
    hint: "Book",
    icon: "book" as IconName,
    run: () => go(to.threads(b.id)),
  }));
  const calendars: PaletteItem = {
    key: "go:calendars",
    label: "Calendar library",
    hint: "Go to",
    icon: "calendar",
    run: () => go(to.calendars()),
  };
  return [
    ...(book ? bookPlaces(book, sinks) : []),
    ...creations(actions),
    ...(book ? graphItems(book, graph, sinks) : []),
    ...castItems(cast, { ...sinks, follow }),
    ...bookItems,
    calendars,
  ];
}

/** Opens on ⌘K / Ctrl+K from anywhere on the page. */
export function usePaletteShortcut(open: () => void) {
  useEffect(() => {
    const onKey = (e: globalThis.KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        open();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);
}

/** What the open palette draws: built only while it is open, and gone when it closes. */
function PaletteBody({ onChosen }: { onChosen: () => void }) {
  const items = usePaletteItems();
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const found = rank(items, query, 40);

  const choose = (item: PaletteItem | undefined) => {
    if (!item) return;
    onChosen();
    item.run();
  };
  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      const step = e.key === "ArrowDown" ? 1 : -1;
      setActive((n) => (found.length ? (n + step + found.length) % found.length : 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      choose(found[active]);
    }
  };

  return (
    <>
      <div className="cw-palette-field">
        <Icon name="search" size={18} />
        <input
          autoFocus
          className="cw-palette-input"
          placeholder="Search threads, scenes, goals, people and books…"
          aria-label="Search or jump to"
          role="combobox"
          aria-expanded="true"
          aria-controls="cw-palette-list"
          aria-activedescendant={
            found[active] ? `cw-palette-${found[active].key}` : undefined
          }
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setActive(0);
          }}
          onKeyDown={onKeyDown}
        />
      </div>
      <ul className="cw-palette-list" id="cw-palette-list" role="listbox">
        {found.map((item, n) => (
          <li
            key={item.key}
            id={`cw-palette-${item.key}`}
            role="option"
            aria-selected={n === active}
            className={`cw-palette-item${n === active ? " is-active" : ""}`}
            onMouseMove={() => setActive(n)}
            onClick={() => choose(item)}
          >
            <Icon name={item.icon} size={16} />
            <span className="cw-palette-label">{item.label}</span>
            <span className="cw-palette-hint">{item.hint}</span>
          </li>
        ))}
        {found.length === 0 ? (
          <li className="cw-palette-empty">Nothing matches “{query}”.</li>
        ) : null}
      </ul>
    </>
  );
}

export function CommandPalette({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="st-overlay" />
        <Dialog.Content className="st-modal cw-palette" aria-describedby={undefined}>
          <Dialog.Title className="st-sr-only">Search or jump to</Dialog.Title>
          <PaletteBody onChosen={() => onOpenChange(false)} />
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
