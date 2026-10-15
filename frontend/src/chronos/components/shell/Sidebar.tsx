// The workspace's left rail: which book, where in it, and the way to anything.
//
// Inside a book it lists the book's sections, with the report's problem count
// always in sight -- a writer should not have to visit the report to learn
// there is something on it. Outside a book it offers the books and the
// calendar library.

import { DropdownMenu } from "radix-ui";
import type { Route } from "../../logic/route";
import { bookOf, to } from "../../logic/route";
import { useBooks, useReport } from "../../hooks/queries";
import { useRoute } from "../../hooks/useRoute";
import { useDeps } from "../../deps";
import { CalendarSwitcher } from "../common/Fields";
import { Link } from "../common/Link";
import { useOptionalBookScope } from "./BookScope";
import { LensPicker } from "./Lens";
import { Icon, type IconName } from "../../../components/ui/Icon";
import { plural } from "../../logic/text";
import { shortcutLabel } from "../common/keys";

interface Section {
  label: string;
  icon: IconName;
  route: Route;
  active: boolean;
  badge?: number;
  tone?: "danger" | "muted";
}

/** The book's sections, which one the route is in, and what each is carrying. */
export function bookSections(route: Route, book: string, problems: number): Section[] {
  const view = route.view;
  return [
    {
      label: "Threads",
      icon: "branch",
      route: to.threads(book),
      active: view === "threads" || view === "plotline",
    },
    { label: "Scenes", icon: "scenes", route: to.scenes(book), active: view === "scenes" },
    { label: "Goals", icon: "target", route: to.goals(book), active: view === "goals" },
    { label: "Story map", icon: "map", route: to.map(book), active: view === "map" },
    {
      label: "Issues",
      icon: "alert",
      route: to.issues(book),
      active: view === "issues",
      badge: problems,
      tone: problems ? "danger" : "muted",
    },
  ];
}

function NavLink({ section }: { section: Section }) {
  return (
    <Link
      className={`cw-nav-link${section.active ? " is-active" : ""}`}
      to={section.route}
      aria-current={section.active ? "page" : undefined}
    >
      <Icon name={section.icon} size={17} />
      <span className="cw-nav-label">{section.label}</span>
      {section.badge ? (
        <span
          className={`cw-nav-badge is-${section.tone ?? "muted"}`}
          aria-label={plural(section.badge, "problem")}
        >
          {section.badge}
        </span>
      ) : null}
    </Link>
  );
}

function BookSwitcher({ book }: { book: string | null }) {
  const { data: books } = useBooks();
  const { go } = useRoute();
  const current = books?.find((b) => b.id === book);
  const label = book ? current?.title || book : "All books";
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger className="cw-book-switch" aria-label="Switch book">
        <span className="cw-book-mark" aria-hidden="true">
          <Icon name="book" size={16} />
        </span>
        <span className="cw-book-switch-text">
          <span className="cw-book-switch-eyebrow">{book ? "Book" : "Chronos"}</span>
          <span className="cw-book-switch-title">{label}</span>
        </span>
        <Icon name="chevronDown" size={14} />
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content className="st-popover cw-menu" align="start" sideOffset={6}>
          <DropdownMenu.Label className="cw-menu-label">Books</DropdownMenu.Label>
          {(books ?? []).map((b) => (
            <DropdownMenu.Item
              key={b.id}
              className="cw-menu-item"
              onSelect={() => go(to.threads(b.id))}
            >
              <Icon name={b.id === book ? "check" : "book"} size={14} />
              {b.title || b.id}
            </DropdownMenu.Item>
          ))}
          <DropdownMenu.Separator className="cw-menu-sep" />
          <DropdownMenu.Item className="cw-menu-item" onSelect={() => go(to.books())}>
            <Icon name="home" size={14} /> All books
          </DropdownMenu.Item>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}

function BookNav({ book }: { book: string }) {
  const { route } = useRoute();
  const scope = useOptionalBookScope();
  const { data: report } = useReport(book, scope?.calendar ?? null);
  const sections = bookSections(route, book, report?.summary.problems ?? 0);
  return (
    <nav className="cw-nav" aria-label="This book">
      {sections.map((s) => (
        <NavLink key={s.label} section={s} />
      ))}
    </nav>
  );
}

export function Sidebar({ onSearch }: { onSearch: () => void }) {
  const { route } = useRoute();
  const { classicUrl, location } = useDeps();
  const scope = useOptionalBookScope();
  const book = bookOf(route);
  const library: Section[] = [
    { label: "Books", icon: "home", route: to.books(), active: route.view === "books" },
    {
      label: "Calendars",
      icon: "calendar",
      route: to.calendars(),
      active: route.view === "calendars",
    },
  ];
  return (
    <aside className="cw-sidebar">
      <BookSwitcher book={book} />
      <button type="button" className="cw-search-trigger" onClick={onSearch}>
        <Icon name="search" size={15} />
        <span>Search or jump to…</span>
        <kbd className="cw-kbd">{shortcutLabel("K")}</kbd>
      </button>
      {book ? <BookNav book={book} /> : null}
      {scope ? (
        <div className="cw-sidebar-block">
          <CalendarSwitcher
            calendars={scope.calendars}
            value={scope.calendar}
            onChange={scope.choose}
          />
          <LensPicker />
        </div>
      ) : null}
      <div className="cw-sidebar-spacer" />
      <nav className="cw-nav cw-nav-library" aria-label="Library">
        <div className="cw-nav-heading">Library</div>
        {library.map((s) => (
          <NavLink key={s.label} section={s} />
        ))}
      </nav>
      <a className="cw-classic-link" href={classicUrl(location.current())}>
        <Icon name="arrowLeft" size={13} /> Classic view
      </a>
    </aside>
  );
}
