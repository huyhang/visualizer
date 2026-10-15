// The workspace's root: the providers every screen expects, around the frame.
// `deps` arrive from outside -- `main.tsx` builds the real ones, tests fakes.

import {
  MutationCache,
  QueryCache,
  QueryClient,
  QueryClientProvider,
} from "@tanstack/react-query";
import { Tooltip } from "radix-ui";
import { useState } from "react";
import { ChronosApiError } from "./api/errors";
import { ChronosDepsProvider, type ChronosDeps } from "./deps";
import { Workspace } from "./components/shell/Workspace";
import { RouteProvider } from "./hooks/useRoute";
import { SessionMemoryProvider } from "./hooks/useSessionMemory";
import { Toaster } from "../components/ui/Toaster";

/** Whether a failure means the session is gone rather than that something was refused. */
export function signedOut(error: unknown): boolean {
  return error instanceof ChronosApiError && error.status === 401;
}

/**
 * The page's cache. A 401 from any read or write means the session expired
 * while the page was open, so it sends the writer to sign in rather than
 * leaving every screen failing quietly; anything else is the screen's to show.
 */
export function defaultQueryClient(onSignedOut: () => void = () => {}): QueryClient {
  const onError = (error: unknown) => {
    if (signedOut(error)) onSignedOut();
  };
  return new QueryClient({
    queryCache: new QueryCache({ onError }),
    mutationCache: new MutationCache({ onError }),
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        refetchOnWindowFocus: true,
        retry: (count, error) => !signedOut(error) && count < 1,
      },
    },
  });
}

export function ChronosApp({ deps, client }: { deps: ChronosDeps; client?: QueryClient }) {
  const [queryClient] = useState(() => client ?? defaultQueryClient(deps.signIn));
  return (
    <QueryClientProvider client={queryClient}>
      <ChronosDepsProvider deps={deps}>
        <Tooltip.Provider delayDuration={300}>
          <Toaster>
            <RouteProvider>
              <SessionMemoryProvider>
                <Workspace />
              </SessionMemoryProvider>
            </RouteProvider>
          </Toaster>
        </Tooltip.Provider>
      </ChronosDepsProvider>
    </QueryClientProvider>
  );
}
