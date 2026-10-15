// The LogosApi in use, handed down rather than imported, so a test supplies its own.

import { createContext, useContext, type ReactNode } from "react";
import type { LogosApi } from "./LogosApi";

const ApiContext = createContext<LogosApi | null>(null);

export function LogosApiProvider({
  api,
  children,
}: {
  api: LogosApi;
  children: ReactNode;
}) {
  return <ApiContext.Provider value={api}>{children}</ApiContext.Provider>;
}

export function useLogosApi(): LogosApi {
  const api = useContext(ApiContext);
  if (!api) throw new Error("useLogosApi() needs a <LogosApiProvider> above it.");
  return api;
}
