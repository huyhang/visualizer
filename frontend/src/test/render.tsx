import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { Tooltip } from "radix-ui";
import type { ReactElement } from "react";
import { ApiProvider } from "../api/context";
import type { ResearchApi } from "../api/ResearchApi";
import { Toaster } from "../components/ui/Toaster";

export function testQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: Infinity },
      mutations: { retry: false },
    },
  });
}

/** Render with the providers a studio component expects around it. */
export function renderWith(ui: ReactElement, api?: ResearchApi) {
  const client = testQueryClient();
  const tree = (
    <QueryClientProvider client={client}>
      <Tooltip.Provider>
        <Toaster>{api ? <ApiProvider api={api}>{ui}</ApiProvider> : ui}</Toaster>
      </Tooltip.Provider>
    </QueryClientProvider>
  );
  return { ...render(tree), client };
}
