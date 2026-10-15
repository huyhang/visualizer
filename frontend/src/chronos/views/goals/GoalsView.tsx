// A book's goals: the dependency diagram, and a card per goal under it.
//
// One request feeds both. The listing returns every goal already read against
// the rest of the book -- what it rests on, what rests on it, who pursues it,
// the scene that delivers it, how deep it sits, what is wrong with it -- so the
// diagram and the list are two readings of one answer and cannot disagree. No
// paging: a dependency graph is only legible whole.
//
// The diagram always shows the whole graph, filter or no filter: hiding half
// the nodes would leave edges pointing at nothing. The filter is for finding a
// goal, so it is the list that narrows.

import { useMemo, useState } from "react";
import type { Goal } from "../../api/types";
import { useGoals } from "../../hooks/queries";
import { useRoute } from "../../hooks/useRoute";
import { inReadingOrder, matchesFilter } from "../../logic/goals/goals";
import { to } from "../../logic/route";
import { plural } from "../../logic/text";
import { SearchField, useDebounced } from "../../components/common/Fields";
import { Page, PageHeader } from "../../components/common/Page";
import { QueryState } from "../../components/common/QueryState";
import { useActions } from "../../components/shell/Actions";
import { useBookScope } from "../../components/shell/BookScope";
import { Button } from "../../../components/ui/Button";
import { EmptyState } from "../../../components/ui/EmptyState";
import { GoalCard } from "./GoalCard";
import { GoalDiagram } from "./GoalDiagram";

const LEDE =
  "What this book is trying to bring about. A goal is drawn below everything it rests on, so the " +
  "diagram reads downward: earlier at the top. Goals that neither rest on anything nor carry " +
  "anything sit together above it.";

function GoalList({
  goals,
  filter,
  selected,
}: {
  goals: Goal[];
  filter: string;
  selected: string | null;
}) {
  const shown = useMemo(
    () => inReadingOrder(goals.filter((g) => matchesFilter(g, filter))),
    [goals, filter],
  );
  if (!shown.length) {
    return (
      <EmptyState icon="search" title="No goal matches">
        Nothing here contains every word of “{filter}”.
      </EmptyState>
    );
  }
  return (
    <div className="cw-goal-list">
      {shown.map((g) => (
        <GoalCard key={g.id} goal={g} open={g.id === selected} />
      ))}
    </div>
  );
}

function Goals({
  goals,
  selected,
  filter,
}: {
  goals: Goal[];
  selected: string | null;
  filter: string;
}) {
  const { id: book, canWrite } = useBookScope();
  const { newGoal } = useActions();
  const { go } = useRoute();
  if (!goals.length) {
    return (
      <EmptyState
        icon="target"
        title="No goals yet"
        action={
          canWrite && newGoal ? (
            <Button variant="primary" icon="plus" onClick={() => newGoal()}>
              New goal
            </Button>
          ) : undefined
        }
      >
        {canWrite
          ? "Name one, and the threads can start pointing at it."
          : "This book has no goals yet."}
      </EmptyState>
    );
  }
  return (
    <>
      <GoalDiagram
        goals={goals}
        selected={selected}
        onPick={(id) => go(to.goals(book, id === selected ? null : id))}
      />
      <div className="cw-section-row">
        <h2 className="cw-section-title">{plural(goals.length, "goal")}</h2>
      </div>
      <GoalList goals={goals} filter={filter} selected={selected} />
    </>
  );
}

export function GoalsView({ selected }: { selected: string | null }) {
  const { id: book, book: record, calendar, canWrite } = useBookScope();
  const { newGoal } = useActions();
  const query = useGoals(book, calendar);
  const [typed, setTyped] = useState("");
  const filter = useDebounced(typed.trim(), 200);
  return (
    <Page label="Goals">
      <PageHeader
        eyebrow={record?.title || book}
        title="Goals"
        subtitle={LEDE}
        actions={
          canWrite && newGoal ? (
            <Button variant="primary" icon="plus" onClick={() => newGoal()}>
              New goal
            </Button>
          ) : null
        }
      >
        <SearchField
          value={typed}
          onChange={setTyped}
          placeholder="Filter goals…"
          label="Filter goals"
        />
      </PageHeader>
      <QueryState query={query}>
        {(goals) => <Goals goals={goals} selected={selected} filter={filter} />}
      </QueryState>
    </Page>
  );
}
