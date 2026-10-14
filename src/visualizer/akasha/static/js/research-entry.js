// The way into the research studio (/studio/<world>, a page of its own drawn
// by the React bundle in frontend/). Offered on a world's page and on the
// categories research fills, and only when a GPU box is configured at all: on
// a NAS-only stack the button would open a studio with nothing it could do.

import { el } from "./dom.js";

// The categories research writes to, where a "Research" button is at home.
export const RESEARCH_CATEGORIES = new Set(["research", "research-inbox", "sources"]);

let configured = null;

/** Whether research is switched on for this stack -- asked once per page load. */
function researchConfigured() {
  configured ??= fetch("research/availability", { headers: { Accept: "application/json" } })
    .then((resp) => (resp.ok ? resp.json() : { state: "off" }))
    .then((body) => body.state !== "off")
    .catch(() => false);
  return configured;
}

/** Add the studio's button to `actions` once we know research is on. */
export async function offerResearch(actions, database) {
  if (!(await researchConfigured())) return;
  actions.prepend(el("a", {
    class: "btn sm secondary", href: `studio/${encodeURIComponent(database)}`,
    title: "Ask the researcher, read cited drafts, and build research notes",
    text: "✦ Research",
  }));
}
