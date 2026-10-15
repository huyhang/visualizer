// The workspace's router: the address bar's hash, read as a `Route`.
//
// Read once, at the top, and shared: if every component subscribed on its own,
// one that re-rendered for another reason between the hash changing and the
// hashchange event would see the new address while its parent still drew the
// old one -- a screen inside a book, mounted outside it. Navigation goes
// through the injected location, so tests drive it in memory.

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useSyncExternalStore,
  type ReactNode,
} from "react";
import { useDeps } from "../deps";
import { hashFor, parseRoute, type Route } from "../logic/route";

export interface Navigation {
  route: Route;
  /** Go to `route`; Back returns here. */
  go: (route: Route) => void;
  /** Say where we are differently, without a new history entry. */
  replace: (route: Route) => void;
  /** The href for `route`, for links that should open in a new tab too. */
  href: (route: Route) => string;
}

const RouteContext = createContext<Navigation | null>(null);

export function RouteProvider({ children }: { children: ReactNode }) {
  const { location } = useDeps();
  const hash = useSyncExternalStore(location.subscribe, location.current);
  const route = useMemo(() => parseRoute(hash), [hash]);
  const go = useCallback((next: Route) => location.push(hashFor(next)), [location]);
  const replace = useCallback((next: Route) => location.replace(hashFor(next)), [location]);
  const navigation = useMemo(
    () => ({ route, go, replace, href: hashFor }),
    [route, go, replace],
  );
  return <RouteContext.Provider value={navigation}>{children}</RouteContext.Provider>;
}

export function useRoute(): Navigation {
  const navigation = useContext(RouteContext);
  if (!navigation) throw new Error("useRoute() needs a <RouteProvider> above it.");
  return navigation;
}
