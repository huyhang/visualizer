// The writing page's entry: read what the Flask shell put on #writer-root and
// the address bar, build the real dependencies, and mount.

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { createHttpApi } from "./api/http";
import { documentVisibility } from "./deps";
import { newBlockId } from "./doc/ids";
import { browserTimer } from "./logic/autosave";
import { storedPreferences } from "./logic/preferences";
import { applyReadingSettings, readingSettings } from "./logic/readingSettings";
import { indexedDbRecovery } from "./logic/recovery";
import { parseRoute } from "./logic/route";
import { WriterApp } from "./WriterApp";
import "./styles/index.css";

const root = document.getElementById("writer-root");
if (root) {
  const { base = "", user = "", akashaUrl = "/" } = root.dataset;
  applyReadingSettings(document.documentElement, readingSettings(window.localStorage));
  const deps = {
    api: createHttpApi({ base, akashaUrl }),
    recovery: indexedDbRecovery(),
    preferences: storedPreferences(window.localStorage, user),
    timer: browserTimer,
    makeId: newBlockId,
    navigate: (url: string) => window.location.assign(url),
    openTab: (url: string) => void window.open(url, "_blank", "noopener"),
    visibility: documentVisibility,
    user,
  };
  createRoot(root).render(
    <StrictMode>
      <WriterApp deps={deps} route={parseRoute(window.location.search)} />
    </StrictMode>,
  );
}
