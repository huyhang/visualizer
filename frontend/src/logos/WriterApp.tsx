// The writing page: everything it depends on handed in, then loading, a
// failure it can explain, a reader sent back to reading, or the workspace.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Tooltip } from "radix-ui";
import { useEffect, useState } from "react";
import { Toaster } from "../components/ui/Toaster";
import { messageOf } from "./api/errors";
import { Workspace } from "./components/writer/Workspace";
import { useDeps, WriterDepsProvider, type WriterDeps } from "./deps";
import { useWorkspace } from "./hooks/useWorkspace";
import type { Route } from "./logic/route";

export function makeQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { staleTime: 10_000, retry: 1, refetchOnWindowFocus: true },
      mutations: { retry: false },
    },
  });
}

function Loading() {
  return (
    <div className="lw-loading" role="status" aria-label="Opening the draft">
      <div className="lw-loading-page">
        <span />
        <span />
        <span />
        <span />
      </div>
    </div>
  );
}

function Failure({
  title,
  message,
  href,
}: {
  title: string;
  message: string;
  href: string;
}) {
  return (
    <div className="lw-failure">
      <p className="lw-eyebrow">Logos</p>
      <h1>{title}</h1>
      <p>{message}</p>
      <a href={href}>← Manuscripts</a>
    </div>
  );
}

function Page({ route }: { route: Route }) {
  const { api, navigate } = useDeps();
  const loaded = useWorkspace(route);
  const readOnly = loaded.data?.kind === "read-only" ? loaded.data.at : null;
  useEffect(() => {
    // Someone who may read but not write is shown the passage, not refused it.
    if (readOnly) navigate(api.readerUrl(readOnly, route.block, route.draft));
  }, [api, navigate, readOnly, route.block, route.draft]);

  if (loaded.isLoading || readOnly) return <Loading />;
  if (loaded.error || !loaded.data || loaded.data.kind !== "ready") {
    return (
      <Failure
        title="This draft could not be opened"
        message={messageOf(loaded.error)}
        href={api.contentsUrl(route.book)}
      />
    );
  }
  return <Workspace workspace={loaded.data.workspace} route={route} />;
}

export function WriterApp({
  deps,
  route,
  queryClient,
}: {
  deps: WriterDeps;
  route: Route | null;
  queryClient?: QueryClient;
}) {
  const [client] = useState(() => queryClient ?? makeQueryClient());
  return (
    <QueryClientProvider client={client}>
      <WriterDepsProvider deps={deps}>
        <Tooltip.Provider delayDuration={350}>
          <Toaster>
            {route ? (
              <Page route={route} />
            ) : (
              <Failure
                title="Which draft?"
                message="This address does not name a section to write."
                href={deps.api.contentsUrl("")}
              />
            )}
          </Toaster>
        </Tooltip.Provider>
      </WriterDepsProvider>
    </QueryClientProvider>
  );
}
