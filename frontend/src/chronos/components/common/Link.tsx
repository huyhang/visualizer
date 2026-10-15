// A link to a place in the workspace. A real anchor, so it can be opened in a
// new tab or copied; a plain click goes through the router instead, so every
// navigation passes the same injected address bar.

import type { AnchorHTMLAttributes, MouseEvent, ReactNode } from "react";
import { useRoute } from "../../hooks/useRoute";
import type { Route } from "../../logic/route";

/** Whether a click asks for something other than "go here": a new tab, a download. */
export function wantsBrowser(
  e: Pick<MouseEvent, "button" | "metaKey" | "ctrlKey" | "shiftKey" | "altKey">,
) {
  return e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey;
}

export function Link({
  to,
  children,
  onClick,
  ...rest
}: { to: Route; children: ReactNode } & Omit<
  AnchorHTMLAttributes<HTMLAnchorElement>,
  "href"
>) {
  const { go, href } = useRoute();
  return (
    <a
      {...rest}
      href={href(to)}
      onClick={(e) => {
        onClick?.(e);
        if (e.defaultPrevented || wantsBrowser(e)) return;
        e.preventDefault();
        go(to);
      }}
    >
      {children}
    </a>
  );
}
