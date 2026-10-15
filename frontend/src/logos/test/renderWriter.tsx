// The whole writing page in jsdom, with every dependency a fake: the API,
// where unsaved words are kept, what the browser remembers, time (run by
// hand), ids and navigation.

import { render } from "@testing-library/react";
import { vi } from "vitest";
import type { WriterDeps } from "../deps";
import type { Timer } from "../logic/autosave";
import { memoryStore, storedPreferences } from "../logic/preferences";
import { memoryRecovery, type RecoveryStore } from "../logic/recovery";
import type { Route } from "../logic/route";
import { makeQueryClient, WriterApp } from "../WriterApp";
import { AT, fakeApi, fakeState, type FakeState } from "./fakeApi";

/** A timer whose callbacks run only when the test says so. */
export function handTimer() {
  let next = 1;
  const queued = new Map<number, () => void>();
  const timer: Timer = {
    set: (run) => {
      const id = next++;
      queued.set(id, run);
      return id;
    },
    clear: (handle) => void queued.delete(handle as number),
  };
  const runAll = () => {
    const due = [...queued.values()];
    queued.clear();
    for (const run of due) run();
  };
  return { timer, runAll, pending: () => queued.size };
}

export interface WriterSetup {
  state?: Partial<FakeState>;
  route?: Partial<Route>;
  recovery?: RecoveryStore;
  store?: ReturnType<typeof memoryStore>;
}

export function renderWriter({ state, route, recovery, store }: WriterSetup = {}) {
  const fake = fakeApi(fakeState(state));
  const clock = handTimer();
  let n = 0;
  const keep = store ?? memoryStore();
  const deps: WriterDeps = {
    api: fake.api,
    recovery: recovery ?? memoryRecovery(),
    preferences: storedPreferences(keep, "mara"),
    timer: clock.timer,
    makeId: () => `new-${(n += 1)}`,
    navigate: vi.fn(),
    openTab: vi.fn(),
    visibility: { visible: () => true, subscribe: () => () => {} },
    user: "mara",
  };
  const client = makeQueryClient();
  client.setDefaultOptions({
    queries: { retry: false, staleTime: Infinity, refetchOnWindowFocus: false },
  });
  const full: Route = { ...AT, draft: null, block: null, panel: null, ...route };
  const view = render(<WriterApp deps={deps} route={full} queryClient={client} />);
  return { ...view, ...fake, deps, clock, store: keep };
}
