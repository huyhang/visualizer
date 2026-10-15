// What Chronos's JSON API answers, as far as the workspace reads it. The
// contract is docs/chronos/openapi.json; these are the fields the page uses,
// not every field the server sends.

export type Severity = "conflict" | "info";

/** A link to an Akasha article: the world, the category and the article. */
export interface EntityRef {
  database: string;
  collection: string;
  id: string;
}

export interface Permissions {
  write: boolean;
  delete: boolean;
}

export interface Me {
  username: string;
  role: string;
}

// -- calendars ---------------------------------------------------------------

export interface CalendarCycle {
  name: string;
  size: number;
}

export interface CalendarDescriptor {
  kind?: "identity" | "mixed_radix" | "gregorian";
  base_unit?: string;
  cycles?: CalendarCycle[];
  epoch_label?: string;
  tick_unit?: "day" | "hour" | "minute";
}

export interface CalendarSource {
  owner: string;
  calendar: string;
  rev?: number;
}

/** A calendar a book keeps: a copy of a library entry, under the book's own id. */
export interface CalendarAttachment {
  id: string;
  label?: string;
  descriptor?: CalendarDescriptor | null;
  from_tick?: number | null;
  until_tick?: number | null;
  origin?: string | null;
  source: CalendarSource;
  primary?: boolean;
}

export interface LibraryCalendar {
  kind: "calendar";
  id: string;
  owner: string;
  qualified_id: string;
  name: string;
  descriptor: CalendarDescriptor;
  notes?: string;
  permissions?: Permissions;
  rev: number;
}

export interface LibraryCalendarWrite {
  name: string;
  descriptor: CalendarDescriptor;
  notes?: string;
}

/** A date keyed by the calendar's own unit names, e.g. `{year: 3, month: 4}`. */
export type DateValue = Record<string, number>;

export interface TickReading {
  calendar: string;
  name: string;
  label: string;
}

export interface TickLabel {
  tick: number;
  label: string;
  parts: string[];
  readings?: TickReading[];
  components?: DateValue | null;
}

export interface ResolvedDates {
  start_tick: number;
  end_tick: number;
  ticks: TickLabel[];
}

// -- books -------------------------------------------------------------------

export interface Book {
  kind: "book";
  id: string;
  title?: string;
  overview?: string;
  terminus?: string | null;
  world?: string | null;
  plotlines: string[];
  status: "consistent" | "conflicted";
  rev: number;
  permissions?: Permissions;
  calendars?: CalendarAttachment[];
}

export interface BookWrite {
  title?: string;
  overview?: string;
  terminus?: string;
  world?: string;
  calendars?: CalendarAttachment[];
}

// -- goals -------------------------------------------------------------------

export interface SceneWhen {
  id: string;
  title: string;
  when?: string;
}

/** A goal as named from somewhere else: a thread's chip, a dependency. */
export interface GoalRef {
  id: string;
  title: string;
  achieved?: boolean;
  missing?: boolean;
  achieved_at?: string | null;
  achieved_scene?: SceneWhen | null;
}

export interface GoalFinding {
  code: string;
  severity: Severity;
  message: string;
  goal?: string | null;
  goals?: string[];
  events?: string[];
  plotlines?: string[];
}

export interface Named {
  id: string;
  title: string;
}

export interface Goal {
  kind: "goal";
  id: string;
  book: string;
  title: string;
  description?: string;
  depends_on: string[];
  dependencies: GoalRef[];
  required_by: GoalRef[];
  achieved_at?: string | null;
  achieved_scene?: SceneWhen | null;
  plotlines: Named[];
  depth: number;
  rev: number;
  status: { state: "open" | "achieved" | "conflicted"; findings: GoalFinding[] };
}

/** A full replace: null clears a field, which is how a scene stops delivering a goal. */
export interface GoalWrite {
  title?: string | null;
  description?: string;
  depends_on?: string[];
  achieved_at?: string | null;
}

// -- plotlines ---------------------------------------------------------------

export interface PlotlineRow {
  id: string;
  book: string;
  name: string;
  overview?: string;
  conflicts: number;
  goals: GoalRef[];
}

export interface PlotlinePage {
  plotlines: PlotlineRow[];
  page: number;
  pages: number;
  per_page: number;
  total: number;
}

export interface EventFinding {
  code: string;
  severity: Severity;
  message: string;
  events: string[];
  refs: EntityRef[];
  doc?: string;
}

export interface SceneWindow {
  earliest?: number | null;
  latest?: number | null;
  earliest_label?: string | null;
  latest_label?: string | null;
  impossible?: boolean;
  message?: string;
}

/** A scene as a thread inlines it (`?expand=events`), read in that thread's context. */
export interface EventSummary {
  id: string;
  title?: string;
  start_tick?: number | null;
  end_tick?: number | null;
  start_label?: string | null;
  end_label?: string | null;
  start_parts?: string[] | null;
  end_parts?: string[] | null;
  location?: EntityRef | null;
  characters?: EntityRef[];
  items?: EntityRef[];
  description_preview?: string;
  shared_with?: string[];
  findings?: EventFinding[];
  is_convergence?: boolean;
  is_divergence?: boolean;
  is_terminus?: boolean;
  owned?: boolean;
  scheduled?: boolean;
  window?: SceneWindow | null;
}

export interface Verdict {
  state: "ok" | "conflicted";
  code?: string;
  message?: string;
}

export interface PlotlineStatus {
  conflicts?: number;
  ordering?: Verdict;
  ends_at_terminus?: Verdict;
  continuation?: Verdict;
  span?: {
    start_tick?: number;
    end_tick?: number;
    start_label?: string;
    end_label?: string;
  };
}

export interface Plotline {
  kind: "plotline";
  id: string;
  book: string;
  title?: string;
  overview?: string;
  events: string[];
  goals: string[];
  goal_refs?: GoalRef[];
  continues_into?: string | null;
  continues_into_at?: string | null;
  continues_into_title?: string | null;
  /** Ids without `?expand=events`; summaries with it. */
  effective_events: (string | EventSummary)[];
  status: PlotlineStatus;
  rev: number;
}

export interface PlotlineWrite {
  title?: string;
  overview?: string;
  events: string[];
  goals?: string[];
  continues_into?: string | null;
  continues_into_at?: string | null;
}

/** A candidate ordering, judged as saving it would judge it. */
export interface PlotlinePreview {
  kind: "plotline-preview";
  id: string;
  title?: string;
  events: string[];
  goals: string[];
  goal_refs?: GoalRef[];
  continues_into?: string | null;
  continues_into_title?: string | null;
  effective_events: EventSummary[];
  status: PlotlineStatus;
}

// -- the book's report -------------------------------------------------------

export interface Issue {
  code: string;
  severity: Severity;
  message: string;
  scene: Named | null;
  events: Named[];
  plotlines: Named[];
  refs: EntityRef[];
  goal: Named | null;
  goals: Named[];
  doc?: string;
}

export interface IssueGroup {
  title: string;
  severity: Severity;
  codes: string[];
  issues: Issue[];
}

export interface BookReport {
  status: "consistent" | "conflicted";
  summary: { problems: number; notes: number; unscheduled: number };
  problems: IssueGroup[];
  notes: IssueGroup[];
  plotlines: { id: string; title?: string; problems: number }[];
}

// -- scenes ------------------------------------------------------------------

export interface SceneEvent {
  kind: "event";
  id: string;
  book: string;
  title?: string;
  location: EntityRef;
  start_tick?: number | null;
  end_tick?: number | null;
  start_label?: string | null;
  end_label?: string | null;
  characters?: EntityRef[];
  items?: EntityRef[];
  description?: string;
  scheduled?: boolean;
  window?: SceneWindow | null;
  rev: number;
}

/** A full replace: null timing is how a scene goes back to being unscheduled. */
export interface EventWrite {
  title?: string | null;
  location: EntityRef;
  start_tick?: number | null;
  end_tick?: number | null;
  start_date?: DateValue | null;
  end_date?: DateValue | null;
  characters?: EntityRef[];
  items?: EntityRef[];
  description?: string;
}

export interface EventRow {
  id: string;
  book: string;
  title: string;
  when: string;
  scheduled: boolean;
  start_tick?: number | null;
  end_tick?: number | null;
  location: string;
  location_ref?: EntityRef;
  plotlines: string[];
}

export interface EventPage {
  events: EventRow[];
  page: number;
  per_page: number;
  total: number;
  pages: number;
}

export interface TimelineEvent extends EventRow {
  start_label: string | null;
  end_label: string | null;
  start_parts: string[] | null;
  end_parts: string[] | null;
}

export interface SceneTimeline {
  events: TimelineEvent[];
  unscheduled: TimelineEvent[];
  bounds: { start_tick: number; end_tick: number };
  total: number;
  plotlines: Named[];
}

// -- the story graph ---------------------------------------------------------

export interface GraphNode {
  id: string;
  title?: string;
  start_tick?: number | null;
  end_tick?: number | null;
  start_label?: string | null;
  end_label?: string | null;
  start_parts?: string[] | null;
  end_parts?: string[] | null;
  scheduled?: boolean;
  is_convergence?: boolean;
  is_divergence?: boolean;
  is_terminus?: boolean;
}

export interface GraphPlotline {
  id: string;
  title?: string;
  events?: string[];
  continues_into?: string | null;
  continues_into_at?: string | null;
  effective_events: string[];
  goals?: string[];
}

export interface GraphEdge {
  from: string;
  to: string;
  plotlines: string[];
}

export interface Graph {
  nodes: GraphNode[];
  edges: GraphEdge[];
  convergence: string[];
  divergence: string[];
  terminus?: string | null;
  plotlines: GraphPlotline[];
  goals?: GoalRef[];
}

// -- Akasha, read through Chronos ---------------------------------------------

export interface Article {
  id: string;
  rev: number;
  document: { title?: string; body?: string; [field: string]: unknown };
}

export interface EntityCandidate {
  database: string;
  collection: string;
  id: string;
  title: string;
}

export interface EntitySuggestions {
  database: string;
  collection: string;
  collections: string[];
  results: EntityCandidate[];
}

export interface World {
  database: string;
  collections: string[];
}
