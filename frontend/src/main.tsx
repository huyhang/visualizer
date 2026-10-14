// The studio's entry: read what the Flask shell put on #studio-root, build the
// real dependencies, and mount.

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { createHttpApi } from "./api/http";
import { App } from "./App";
import { browserId, localStore } from "./hooks/useComposition";
import "./styles/index.css";

const root = document.getElementById("studio-root");
if (root) {
  const { world = "", apiRoot = "", akashaRoot = "/" } = root.dataset;
  const api = createHttpApi({ apiRoot, akashaRoot, world });
  createRoot(root).render(
    <StrictMode>
      <App api={api} store={localStore(world)} newId={browserId} />
    </StrictMode>,
  );
}
