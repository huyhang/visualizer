import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Tooltip } from "radix-ui";
import { useState } from "react";
import { ApiProvider } from "./api/context";
import type { ResearchApi } from "./api/ResearchApi";
import type { NewId } from "./logic/compose";
import type { CompositionStore } from "./hooks/useComposition";
import { Studio } from "./components/Studio";
import { Toaster } from "./components/ui/Toaster";

export function makeQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { staleTime: 10_000, retry: 1, refetchOnWindowFocus: true },
      mutations: { retry: false },
    },
  });
}

/** Everything the studio depends on, handed in: the api, where the note is kept, ids. */
export function App({
  api,
  store,
  newId,
  queryClient,
}: {
  api: ResearchApi;
  store: CompositionStore;
  newId: NewId;
  queryClient?: QueryClient;
}) {
  const [client] = useState(() => queryClient ?? makeQueryClient());
  return (
    <QueryClientProvider client={client}>
      <ApiProvider api={api}>
        <Tooltip.Provider delayDuration={350}>
          <Toaster>
            <Studio store={store} newId={newId} />
          </Toaster>
        </Tooltip.Provider>
      </ApiProvider>
    </QueryClientProvider>
  );
}
