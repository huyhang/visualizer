// The workspace's frame: the sidebar, the screen the address names, and the
// inspector beside it. Inside a book everything shares one BookScope, so the
// calendar picked in the sidebar is the calendar every screen reads through.

import { useCallback, useEffect, useState, type ReactNode } from "react";
import { useRoute } from "../../hooks/useRoute";
import { bookOf } from "../../logic/route";
import { Inspector } from "../inspector/Inspector";
import { RouteView } from "../../views/RouteView";
import { BookScope } from "./BookScope";
import { CommandPalette, usePaletteShortcut } from "./CommandPalette";
import { Editors } from "./Editors";
import { InspectorProvider, useInspector } from "./InspectorContext";
import { LensProvider } from "./Lens";
import { Sidebar } from "./Sidebar";

/** Shut the inspector when the book changes: what it showed belongs to the old one. */
function useCloseOnBookChange(book: string | null) {
  const { close } = useInspector();
  useEffect(() => close(), [book, close]);
}

function Frame() {
  const { route } = useRoute();
  const { target } = useInspector();
  const [palette, setPalette] = useState(false);
  const openPalette = useCallback(() => setPalette(true), []);
  usePaletteShortcut(openPalette);
  useCloseOnBookChange(bookOf(route));
  return (
    <div className={`cw-frame${target ? " has-inspector" : ""}`}>
      <Sidebar onSearch={openPalette} />
      <main className="cw-main" id="cw-main">
        <RouteView route={route} />
      </main>
      <Inspector />
      <CommandPalette open={palette} onOpenChange={setPalette} />
    </div>
  );
}

function MaybeBook({ book, children }: { book: string | null; children: ReactNode }) {
  return book ? (
    <BookScope id={book} key={book}>
      {children}
    </BookScope>
  ) : (
    <>{children}</>
  );
}

export function Workspace() {
  const { route } = useRoute();
  const book = bookOf(route);
  return (
    <MaybeBook book={book}>
      <LensProvider>
        <InspectorProvider>
          <Editors>
            <Frame />
          </Editors>
        </InspectorProvider>
      </LensProvider>
    </MaybeBook>
  );
}
