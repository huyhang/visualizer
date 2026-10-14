// The ResearchApi in use, handed down rather than imported, so a test (or a
// future surface on another world) supplies its own.

import { createContext, useContext, type ReactNode } from "react";
import type { ResearchApi } from "./ResearchApi";

const ApiContext = createContext<ResearchApi | null>(null);

export function ApiProvider({ api, children }: { api: ResearchApi; children: ReactNode }) {
  return <ApiContext.Provider value={api}>{children}</ApiContext.Provider>;
}

export function useApi(): ResearchApi {
  const api = useContext(ApiContext);
  if (!api) throw new Error("useApi() needs an <ApiProvider> above it.");
  return api;
}
