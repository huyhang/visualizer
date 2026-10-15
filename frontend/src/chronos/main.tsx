// The workspace's entry: read what the Flask shell put on #chronos-root, build
// the real dependencies, and mount.

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { createHttpApi } from "./api/http";
import { ChronosApp } from "./ChronosApp";
import { browserStore, windowLocation } from "./deps";
import "./styles/index.css";

const root = document.getElementById("chronos-root");
if (root) {
  const { base = "", user = "", akashaUrl = "/", classicUrl = "/" } = root.dataset;
  const deps = {
    api: createHttpApi({ base }),
    location: windowLocation(window),
    store: browserStore(window.localStorage),
    user,
    akashaUrl,
    classicUrl: (hash: string) => classicUrl + hash,
    signIn: () => window.location.assign(`${base}/login`),
  };
  createRoot(root).render(
    <StrictMode>
      <ChronosApp deps={deps} />
    </StrictMode>,
  );
}
