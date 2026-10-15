// Everything the workspace asks of Chronos. Components and hooks receive this
// through the workspace's dependencies; the page builds the HTTP one, tests
// build a fake. Every write to something that exists takes the revision the
// page read, so a save that raced a collaborator is refused, not lost.

import type {
  Article,
  Book,
  BookReport,
  BookWrite,
  DateValue,
  EntitySuggestions,
  EventPage,
  EventWrite,
  Goal,
  GoalWrite,
  Graph,
  LibraryCalendar,
  LibraryCalendarWrite,
  Me,
  Plotline,
  PlotlinePage,
  PlotlinePreview,
  PlotlineWrite,
  ResolvedDates,
  SceneEvent,
  SceneTimeline,
  TickLabel,
  World,
} from "./types";

/** Which of a book's calendars to read ticks through; omitted means its primary one. */
export interface ViewOptions {
  calendar?: string | null;
}

export interface PageOptions extends ViewOptions {
  filter?: string;
  page?: number;
  perPage?: number;
}

export interface EntityQuery {
  q?: string;
  collection?: string;
  database?: string;
}

export interface ChronosApi {
  me(): Promise<Me>;

  listBooks(): Promise<Book[]>;
  getBook(book: string): Promise<Book>;
  createBook(book: string, body: BookWrite): Promise<Book>;
  /** A full replace: whatever the body omits is erased. */
  updateBook(book: string, body: BookWrite, rev: number): Promise<Book>;
  /** The book and everything in it, with no history behind it. */
  deleteBook(book: string, rev: number): Promise<void>;
  setTerminus(book: string, event: string): Promise<Book>;

  listPlotlines(book: string, options?: PageOptions): Promise<PlotlinePage>;
  getPlotline(book: string, id: string, options?: ViewOptions): Promise<Plotline>;
  createPlotline(book: string, id: string, body: PlotlineWrite): Promise<Plotline>;
  updatePlotline(
    book: string,
    id: string,
    body: PlotlineWrite,
    rev: number,
  ): Promise<Plotline>;
  /** `inline` folds the thread into the ones continuing into it, so they survive. */
  deletePlotline(book: string, id: string, rev: number, inline?: boolean): Promise<void>;
  /** What saving this candidate would make of it. Writes nothing. */
  previewPlotline(
    book: string,
    candidate: PlotlineWrite & { id?: string },
    options?: ViewOptions,
  ): Promise<PlotlinePreview>;

  bookIssues(book: string, options?: ViewOptions): Promise<BookReport>;

  listEvents(book: string, options?: PageOptions): Promise<EventPage>;
  timelineEvents(book: string, options?: PageOptions): Promise<SceneTimeline>;
  getEvent(book: string, id: string, options?: ViewOptions): Promise<SceneEvent>;
  createEvent(
    book: string,
    id: string,
    body: EventWrite,
    options?: ViewOptions,
  ): Promise<SceneEvent>;
  updateEvent(
    book: string,
    id: string,
    body: EventWrite,
    rev: number,
    options?: ViewOptions,
  ): Promise<SceneEvent>;
  /** `detach` first takes the scene out of every thread that lists it. */
  deleteEvent(book: string, id: string, rev: number, detach?: boolean): Promise<void>;

  listGoals(book: string, options?: ViewOptions): Promise<Goal[]>;
  getGoal(book: string, id: string, options?: ViewOptions): Promise<Goal>;
  createGoal(book: string, id: string, body: GoalWrite): Promise<Goal>;
  updateGoal(book: string, id: string, body: GoalWrite, rev: number): Promise<Goal>;
  deleteGoal(book: string, id: string, rev: number, detach?: boolean): Promise<void>;

  getGraph(book: string, options?: ViewOptions): Promise<Graph>;

  getEntity(
    book: string,
    database: string,
    collection: string,
    id: string,
  ): Promise<Article>;
  searchEntities(book: string, query: EntityQuery): Promise<EntitySuggestions>;
  listWorlds(): Promise<World[]>;

  formatTicks(book: string, ticks: number[], options?: ViewOptions): Promise<TickLabel[]>;
  resolveDates(
    book: string,
    timeframe: { start_date?: DateValue; end_date?: DateValue },
    options?: ViewOptions,
  ): Promise<ResolvedDates>;

  listCalendars(): Promise<LibraryCalendar[]>;
  createCalendar(
    owner: string,
    id: string,
    body: LibraryCalendarWrite,
  ): Promise<LibraryCalendar>;
  updateCalendar(
    owner: string,
    id: string,
    body: LibraryCalendarWrite,
    rev: number,
  ): Promise<LibraryCalendar>;
  deleteCalendar(owner: string, id: string, rev: number): Promise<void>;
  shareCalendar(owner: string, id: string, username: string, role?: string): Promise<void>;
  unshareCalendar(owner: string, id: string, username: string): Promise<void>;
}
