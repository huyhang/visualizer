// Mount the workspace, or one piece of it, over fakes: the fake API, an
// address bar in memory and a store that forgets.

import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { ChronosApp } from "../ChronosApp";
import { ChronosDepsProvider, type ChronosDeps } from "../deps";
import { testQueryClient } from "../../test/render";
import { fakeApi, type FakeApi } from "./fakeApi";
import { memoryLocation, memoryStore } from "./memoryStore";
import { QueryClientProvider } from "@tanstack/react-query";
import { Tooltip } from "radix-ui";
import { Toaster } from "../../components/ui/Toaster";
import { RouteProvider } from "../hooks/useRoute";
import { SessionMemoryProvider } from "../hooks/useSessionMemory";

export interface Harness {
  api: FakeApi;
  location: ReturnType<typeof memoryLocation>;
  store: ReturnType<typeof memoryStore>;
  deps: ChronosDeps;
}

export function harness(
  hash = "#/",
  api: FakeApi = fakeApi(),
  remembered: Record<string, string> = {},
): Harness {
  const location = memoryLocation(hash);
  const store = memoryStore(remembered);
  const deps: ChronosDeps = {
    api,
    location,
    store,
    user: "mara",
    akashaUrl: "/akasha/",
    classicUrl: (h) => `/classic${h}`,
    signIn: vi.fn(),
  };
  return { api, location, store, deps };
}

/** The whole workspace at `hash`, with what the browser already remembers. */
export function renderWorkspace(
  hash = "#/",
  api?: FakeApi,
  remembered?: Record<string, string>,
) {
  const h = harness(hash, api, remembered);
  const client = testQueryClient();
  return { ...h, client, ...render(<ChronosApp deps={h.deps} client={client} />) };
}

/** One component, inside the providers it expects. */
export function renderWithDeps(ui: ReactElement, h: Harness = harness()) {
  const client = testQueryClient();
  const result = render(
    <QueryClientProvider client={client}>
      <ChronosDepsProvider deps={h.deps}>
        <Tooltip.Provider>
          <Toaster>
            <RouteProvider>
              <SessionMemoryProvider>{ui}</SessionMemoryProvider>
            </RouteProvider>
          </Toaster>
        </Tooltip.Provider>
      </ChronosDepsProvider>
    </QueryClientProvider>,
  );
  return { ...h, client, ...result };
}
