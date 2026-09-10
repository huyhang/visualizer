// The Akasha side panel: what canon the selected words might name, and what a
// linked phrase already points at.
//
// Sibling of `coachpanel.js`, and injected the same way: it receives a search
// function, callbacks for the three actions, and the element builders. It
// never touches the editor, the API module or the DOM beyond the node handed
// to it, so every state it can be in -- searching, empty, failed, listing,
// showing one mention -- is reachable from a test.

import { el as browserEl, fill as browserFill } from "./dom.js";

export function createAkashaPanel({
  body, focus, search, ui = { el: browserEl, fill: browserFill },
}) {
  const { el, fill } = ui;

  const note = (className, text) => fill(body, [el("p", { class: className, text })]);

  function fieldList(fields) {
    if (!fields || !fields.length) return null;
    return el("dl", { class: "entity-fields" }, fields.flatMap((field) => [
      el("dt", { text: field.name }),
      el("dd", { text: field.value }),
    ]));
  }

  function entityCard(entity, { onOpen, onLink, canLink }) {
    return el("article", { class: "entity-result" }, [
      el("strong", { text: entity.title }),
      el("small", { text: `${entity.database_title} / ${entity.collection_title}` }),
      fieldList(entity.fields),
      el("div", { class: "entity-actions" }, [
        el("button", {
          class: "btn sm", type: "button", text: "Link mention",
          disabled: !canLink,
          title: canLink
            ? "Keep this selection linked to Akasha"
            : "Select within one paragraph to link",
          onclick: () => onLink(entity),
        }),
        el("button", {
          class: "btn ghost sm", type: "button", text: "Open article",
          onclick: () => onOpen(entity),
        }),
      ]),
    ]);
  }

  async function showLookup(selection, { onOpen, onLink }) {
    focus();
    fill(body, [
      el("p", { class: "writer-context-kicker", text: `Selected: “${selection.text}”` }),
      el("p", { class: "muted", text: "Searching Akasha..." }),
    ]);
    try {
      const payload = await search(selection.text);
      const entities = (payload && payload.entities) || [];
      if (!entities.length) {
        note("muted", "No readable Akasha entity matched.");
        return;
      }
      // Linking rewrites one range, so it needs a selection inside one block.
      fill(body, entities.map((entity) => entityCard(entity, {
        onOpen, onLink, canLink: Boolean(selection.block),
      })));
    } catch (error) {
      note("form-error", (error && error.message) || "Akasha lookup failed.");
    }
  }

  function showMention(ref, { onOpen, onUnlink }) {
    focus();
    fill(body, [
      el("p", { class: "writer-context-kicker", text: `Linked: “${ref.text}”` }),
      el("article", { class: "entity-result" }, [
        el("strong", { text: ref.text }),
        el("small", { text: `${ref.database} / ${ref.collection} / ${ref.id}` }),
        el("div", { class: "entity-actions" }, [
          el("button", {
            class: "btn ghost sm", type: "button", text: "Open article",
            onclick: () => onOpen(ref),
          }),
          el("button", {
            class: "btn ghost sm", type: "button", text: "Unlink",
            title: "Keep the words, remove the Akasha reference",
            onclick: () => {
              if (!onUnlink()) return;
              note("muted",
                `“${ref.text}” is no longer linked. The words are unchanged.`);
            },
          }),
        ]),
      ]),
    ]);
  }

  return { showLookup, showMention };
}
