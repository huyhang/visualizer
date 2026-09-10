// The authoring workspace. It owns UI orchestration; document conversion,
// comparison and recovery stay in small injected/pure modules beside it.

import { api } from "./api.js";
import { createCoachPanel } from "./coachpanel.js";
import { compareDocuments } from "./comparison.js";
import { el, fill } from "./dom.js";
import {
  caretPosition,
  documentFromEditor,
  linkMention,
  mentionAt,
  mentionRef,
  placeCaret,
  renderEditorDocument,
  selectedProse,
  unlinkMention,
  wordCount,
} from "./editor.js";
import { createAutosave, createRecoveryStore, recoveryKey } from "./recovery.js";
import { sectionLabel, sectionName } from "./navigation.js";
import { filterOutline } from "./outline.js";

const STATUS = {
  local: "Saved on this device",
  saving: "Saving...",
  saved: "Saved",
  offline: "Offline - saved on this device",
  conflict: "Conflict preserved",
  invalid: "Needs attention",
};

export const writerUrl = (base, book, volume, section, draft = null) => {
  const query = { book, volume, section, mode: "write" };
  if (draft) query.draft = draft;
  return `${base}/?${new URLSearchParams(query)}`;
};

function formatButton(label, command, title = label) {
  return el("button", {
    class: "writer-tool", type: "button", text: label, title,
    onmousedown: (event) => event.preventDefault(),
    onclick: () => document.execCommand(command, false, null),
  });
}

function outlineVolume(volume, manuscript, current, base, navigate, createChapter, filtering) {
  return el("section", { class: "writer-volume" }, [
    el("h2", { text: volume.title }),
    el("ol", {}, volume.sections.map((section) => el("li", {}, [
      el("a", {
        class: section.id === current.section.id && volume.id === current.volume.id ? "current" : "",
        href: writerUrl(base, manuscript.book, volume.id, section.id),
        onclick: navigate,
      }, [
        el("span", { text: sectionName(section) }),
        section.title ? el("small", { text: sectionLabel(section) }) : null,
      ]),
    ]))),
    // Adding a chapter to a filtered view lands it somewhere you cannot see.
    filtering ? null : el("button", {
      class: "new-chapter", type: "button", text: "+ New chapter",
      onclick: () => createChapter(volume),
    }),
  ]);
}

function outline(manuscript, current, base, navigate, createChapter) {
  const volumes = el("div", { class: "writer-outline-volumes" });
  const paint = (query) => {
    const shown = filterOutline(manuscript, query);
    fill(volumes, shown.length
      ? shown.map((volume) => outlineVolume(
        volume, manuscript, current, base, navigate, createChapter, Boolean(query.trim()),
      ))
      : [el("p", { class: "muted", text: "No chapter matches that." })]);
  };
  const search = el("input", {
    class: "writer-outline-search", type: "search", placeholder: "Find a chapter",
    "aria-label": "Filter the outline",
    oninput: (event) => paint(event.target.value),
  });
  paint("");
  return el("nav", { class: "writer-outline", "aria-label": "Manuscript outline" }, [
    el("div", { class: "writer-panel-head" }, [
      el("strong", { text: "Outline" }),
      el("button", { class: "writer-panel-close", type: "button", text: "x",
        "aria-label": "Close outline", onclick: () => document.body.classList.remove("show-writer-outline") }),
    ]),
    search,
    volumes,
  ]);
}

function contextPanel() {
  const body = el("div", { class: "writer-context-body" });
  const tabs = ["Akasha", "Coach"].map((name, index) => el("button", {
    class: `writer-tab${index === 0 ? " active" : ""}`,
    type: "button",
    text: name,
    onclick: () => {
      for (const tab of tabs) tab.classList.toggle("active", tab === tabs[index]);
      body.dataset.tab = name.toLowerCase();
      body.dispatchEvent(new CustomEvent("writer:tab", { detail: name.toLowerCase() }));
    },
  }));
  return {
    body,
    node: el("aside", { class: "writer-context", "aria-label": "Writing tools" }, [
      el("div", { class: "writer-panel-head" }, [
        el("div", { class: "writer-tabs" }, tabs),
        el("button", { class: "writer-panel-close", type: "button", text: "x",
          "aria-label": "Close writing tools", onclick: () => document.body.classList.remove("show-writer-context") }),
      ]),
      body,
    ]),
    select(name) { tabs[name === "coach" ? 1 : 0].click(); },
  };
}

function comparisonDialog(drafts, onCompare) {
  const left = el("select", {}, drafts.map((draft) => el("option", {
    value: draft.id, text: `${draft.name}${draft.primary ? " (Primary)" : ""}`,
  })));
  const right = el("select", {}, drafts.map((draft) => el("option", {
    value: draft.id, text: `${draft.name}${draft.primary ? " (Primary)" : ""}`,
  })));
  if (drafts[1]) right.value = drafts[1].id;
  const results = el("div", { class: "draft-comparison-results" });
  const dialog = el("dialog", { class: "draft-comparison" }, [
    el("div", { class: "compare-head" }, [
      el("h2", { text: "Compare drafts" }),
      el("button", { class: "icon-btn", type: "button", text: "x",
        "aria-label": "Close comparison", onclick: () => dialog.close() }),
    ]),
    el("div", { class: "compare-pickers" }, [left, right, el("button", {
      class: "btn", type: "button", text: "Compare",
      onclick: () => onCompare(left.value, right.value, results),
    })]),
    results,
  ]);
  document.body.appendChild(dialog);
  return dialog;
}

// The empty side of a structural difference is a placeholder, not prose, so it
// never wears the row's status colour.
function compareCell(text, status) {
  return el("p", {
    class: `compare-block ${text ? status : "absent"}`,
    text: text || "— not in this draft —",
  });
}

function paintComparison(target, left, right, compared) {
  const stats = (value) => `${value.words} words | ${value.paragraphs} paragraphs | ${value.averageSentenceWords} words/sentence`;
  fill(target, [
    el("div", { class: "compare-stats" }, [
      el("span", { text: `${left.name}: ${stats(compared.left)}` }),
      el("span", { text: `${right.name}: ${stats(compared.right)}` }),
    ]),
    el("div", { class: "compare-grid" }, compared.rows.flatMap((row) => [
      compareCell(row.left, row.status),
      compareCell(row.right, row.status),
    ])),
  ]);
}

function replaceText(block, before, after) {
  const walker = document.createTreeWalker(block, NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    const node = walker.currentNode;
    const at = node.nodeValue.indexOf(before);
    if (at < 0) continue;
    node.nodeValue = node.nodeValue.slice(0, at) + after + node.nodeValue.slice(at + before.length);
    return true;
  }
  return false;
}

function openArticle(akashaUrl, entity) {
  const base = akashaUrl.endsWith("/") ? akashaUrl : `${akashaUrl}/`;
  const route = [entity.database, entity.collection, entity.id].map(encodeURIComponent).join("/");
  window.open(`${base}#/${route}`, "_blank", "noopener");
}

function askDraftName(heading, value = "") {
  return new Promise((resolve) => {
    const input = el("input", {
      class: "jump-search", value, maxlength: "120", required: true,
      "aria-label": "Draft name",
    });
    const dialog = el("dialog", { class: "settings writer-name-dialog" });
    const finish = (answer) => {
      dialog.close();
      dialog.remove();
      resolve(answer);
    };
    const form = el("form", { method: "dialog", onsubmit: (event) => {
      event.preventDefault();
      const name = input.value.trim();
      if (name) finish(name);
    } }, [
      el("div", { class: "settings-head" }, [
        el("h2", { text: heading }),
        el("button", { class: "icon-btn", type: "button", text: "x",
          "aria-label": "Cancel", onclick: () => finish(null) }),
      ]),
      input,
      el("div", { class: "settings-actions" }, [
        el("button", { class: "btn ghost", type: "button", text: "Cancel", onclick: () => finish(null) }),
        el("button", { class: "btn", type: "submit", text: "Continue" }),
      ]),
    ]);
    dialog.appendChild(form);
    document.body.appendChild(dialog);
    dialog.addEventListener("cancel", (event) => { event.preventDefault(); finish(null); }, { once: true });
    dialog.showModal();
    input.select();
  });
}

function availableId(title, known, fallback) {
  const stem = title.toLowerCase().normalize("NFKD")
    .replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || fallback;
  let candidate = stem;
  let suffix = 2;
  while (known.has(candidate)) candidate = `${stem}-${suffix++}`;
  return candidate;
}

const emptyDocument = () => ({ version: 1, type: "doc", content: [] });

export async function beginWriting(manuscript, base) {
  const title = await askDraftName("Name the new chapter", "Untitled chapter");
  if (!title) return;
  let volume = manuscript.volumes[manuscript.volumes.length - 1];
  if (!volume) {
    const id = "volume-1";
    volume = await api.createVolume(manuscript.book, id, { title: "Volume One", overview: "" });
  }
  const known = new Set(volume.sections.map((item) => item.id));
  const section = availableId(title, known, "chapter");
  await api.createSection(manuscript.book, volume.id, section, {
    kind: "chapter", title, overview: "", event_ids: [], document: emptyDocument(),
  });
  window.location.href = writerUrl(base, manuscript.book, volume.id, section);
}

export async function mountWriter({
  container, manuscript, entry, section, user, base, akashaUrl, onDone,
}) {
  container.classList.add("writer-content");
  const listing = await api.drafts(manuscript.book, entry.volume.id, section.id);
  let sectionRev = listing.section_rev;
  let drafts = listing.drafts;
  const requested = new URLSearchParams(window.location.search).get("draft");
  let current = drafts.find((draft) => draft.id === requested)
    || drafts.find((draft) => draft.primary) || drafts[0];
  let draft = await api.draft(manuscript.book, entry.volume.id, section.id, current.id);
  let selection = null;
  let coachTimer = null;
  const dialectKey = `logos-writing-dialect:${encodeURIComponent(user)}`;
  const ignoredKey = `logos-writing-ignored:${encodeURIComponent(user)}`;
  let dialect = "en-US";
  let ignored = new Set();
  try { dialect = localStorage.getItem(dialectKey) || dialect; } catch (_error) { /* optional */ }
  try { ignored = new Set(JSON.parse(localStorage.getItem(ignoredKey) || "[]")); } catch (_error) { /* optional */ }
  const recovery = createRecoveryStore();
  const key = recoveryKey({
    user, book: manuscript.book, volume: entry.volume.id, section: section.id, draft: draft.id,
  });

  const status = el("span", { class: "writer-save-status", text: "Saved" });
  const count = el("span", { class: "writer-word-count" });
  const title = el("input", {
    class: "writer-title", value: section.title || "", maxlength: "300",
    placeholder: sectionLabel(section), "aria-label": "Section title",
  });
  const editor = el("div", {
    class: "draft-editor prose", contenteditable: "true", spellcheck: "true",
    role: "textbox", "aria-multiline": "true", "aria-label": `Edit ${sectionName(section)}`,
  });
  const context = contextPanel();
  const draftSelect = el("select", { class: "draft-select", "aria-label": "Current draft" });
  const primaryBadge = el("span", { class: "primary-badge", text: "Primary" });
  const conflictAction = el("button", {
    class: "btn sm", type: "button", text: "Preserve as new draft", hidden: true,
  });
  const contextMenu = el("div", {
    class: "writer-context-menu", role: "menu", hidden: true,
    "aria-label": "Manuscript actions",
  });
  document.body.appendChild(contextMenu);
  const closeContextMenu = () => {
    contextMenu.hidden = true;
    fill(contextMenu, []);
  };

  const setStatus = (state, error = null) => {
    status.dataset.state = state;
    status.textContent = STATUS[state] || state;
    status.title = error ? error.message : "";
    conflictAction.hidden = state !== "conflict";
  };
  const snapshot = () => ({
    document: documentFromEditor(editor),
    name: draft.name,
    title: title.value.trim(),
    draftRev: draft.rev,
    caret: caretPosition(editor, window.getSelection()),
    savedAt: new Date().toISOString(),
  });
  const updateCount = () => { count.textContent = `${wordCount(documentFromEditor(editor)).toLocaleString()} words`; };

  const autosave = createAutosave({
    saveLocal: (value) => value ? recovery.set(key, value) : recovery.remove(key),
    saveRemote: async (value, urgent) => {
      const saved = await api.saveDraft(
        manuscript.book, entry.volume.id, section.id, draft.id,
        { name: value.name, document: value.document }, draft.rev, urgent,
      );
      draft = saved;
      sectionRev = saved.section_rev;
      const row = drafts.find((item) => item.id === draft.id);
      if (row) Object.assign(row, saved);
      if (value.title !== (section.title || "")) {
        const updated = await api.updateSectionMetadata(
          manuscript.book, entry.volume.id, section.id,
          { title: value.title || null }, sectionRev,
        );
        section = updated;
        sectionRev = updated.rev;
      }
    },
    onState: setStatus,
  });

  const changed = () => {
    updateCount();
    autosave.schedule(snapshot());
    clearTimeout(coachTimer);
    coachTimer = setTimeout(() => reviewWriting(), 1800);
  };

  const renderDraftOptions = () => {
    fill(draftSelect, drafts.map((item) => el("option", {
      value: item.id,
      text: `${item.name}${item.primary ? " (Primary)" : ""}`,
    })));
    draftSelect.value = draft.id;
    primaryBadge.hidden = !draft.primary;
  };

  const showAkashaPrompt = () => {
    if (!selection) return;
    context.select("akasha");
    document.body.classList.add("show-writer-context");
    fill(context.body, [
      el("p", { class: "writer-context-kicker", text: `Selected: “${selection.text}”` }),
      el("p", { class: "muted", text: "Searching Akasha..." }),
    ]);
    api.entities(manuscript.book, selection.text).then((payload) => {
      if (!payload.entities.length) {
        fill(context.body, [el("p", { class: "muted", text: "No readable Akasha entity matched." })]);
        return;
      }
      fill(context.body, payload.entities.map((entity) => el("article", { class: "entity-result" }, [
        el("strong", { text: entity.title }),
        el("small", { text: `${entity.database_title} / ${entity.collection_title}` }),
        entity.fields && entity.fields.length
          ? el("dl", { class: "entity-fields" }, entity.fields.flatMap((field) => [
            el("dt", { text: field.name }),
            el("dd", { text: field.value }),
          ]))
          : null,
        el("div", { class: "entity-actions" }, [
          el("button", {
            class: "btn sm", type: "button", text: "Link mention",
            disabled: !selection.block,
            title: selection.block ? "Keep this selection linked to Akasha" : "Select within one paragraph to link",
            onclick: () => {
              if (linkMention(selection, entity)) changed();
            },
          }),
          el("button", { class: "btn ghost sm", type: "button", text: "Open article",
            onclick: () => openArticle(akashaUrl, entity) }),
        ]),
      ])));
    }).catch((error) => fill(context.body, [
      el("p", { class: "form-error", text: error.message || "Akasha lookup failed." }),
    ]));
  };

  // Clicking words that are already linked: the two things worth offering are
  // the article behind them and a way to take the link off again.
  const showMentionPanel = (element) => {
    const ref = mentionRef(element);
    context.select("akasha");
    document.body.classList.add("show-writer-context");
    fill(context.body, [
      el("p", { class: "writer-context-kicker", text: `Linked: “${ref.text}”` }),
      el("article", { class: "entity-result" }, [
        el("strong", { text: ref.text }),
        el("small", { text: `${ref.database} / ${ref.collection} / ${ref.id}` }),
        el("div", { class: "entity-actions" }, [
          el("button", {
            class: "btn ghost sm", type: "button", text: "Open article",
            onclick: () => openArticle(akashaUrl, ref),
          }),
          el("button", {
            class: "btn ghost sm", type: "button", text: "Unlink",
            title: "Keep the words, remove the Akasha reference",
            onclick: () => {
              if (!unlinkMention(element)) return;
              changed();
              fill(context.body, [el("p", {
                class: "muted",
                text: `“${ref.text}” is no longer linked. The words are unchanged.`,
              })]);
            },
          }),
        ]),
      ]),
    ]);
  };

  const menuItem = (label, run) => el("button", {
    class: "writer-menu-item", type: "button", role: "menuitem", text: label,
    // Keep the selection alive: focus must not leave the prose on mousedown,
    // or the range the action is about is gone before the click lands.
    onmousedown: (event) => event.preventDefault(),
    onclick: () => { closeContextMenu(); run(); },
  });

  const contextActions = (event) => {
    const items = [];
    const mention = mentionAt(event.target, editor);
    if (mention) {
      const ref = mentionRef(mention);
      items.push(menuItem(`Open “${ref.text}” in Akasha`, () => openArticle(akashaUrl, ref)));
      items.push(menuItem("Unlink these words", () => {
        if (unlinkMention(mention)) changed();
      }));
    }
    const found = selectedProse(editor, window.getSelection());
    if (found) {
      selection = found;
      items.push(menuItem(`Look up “${found.text}” in Akasha`, showAkashaPrompt));
    }
    return items;
  };

  // Right-click is only intercepted when there is something manuscript-specific
  // to offer. Otherwise the browser's own menu stands, which is what carries
  // paste and the spellchecker's suggestions -- worth more than a tidy rule.
  const openContextMenu = (event) => {
    const items = contextActions(event);
    if (!items.length) return;
    event.preventDefault();
    fill(contextMenu, items);
    contextMenu.hidden = false;
    const { offsetWidth, offsetHeight } = contextMenu;
    contextMenu.style.left = `${Math.max(8, Math.min(event.clientX, window.innerWidth - offsetWidth - 8))}px`;
    contextMenu.style.top = `${Math.max(8, Math.min(event.clientY, window.innerHeight - offsetHeight - 8))}px`;
    items[0].focus({ preventScroll: true });
  };

  const remember = (key, value) => {
    try { localStorage.setItem(key, value); } catch (_error) { /* optional */ }
  };
  const coach = createCoachPanel({
    body: context.body,
    requestReview: (chosen) => api.writingReview(
      manuscript.book, documentFromEditor(editor), chosen,
    ),
    preferences: {
      dialect: () => dialect,
      setDialect: (value) => { dialect = value; remember(dialectKey, value); },
      isIgnored: (title) => ignored.has(title),
      ignore: (title) => {
        ignored.add(title);
        remember(ignoredKey, JSON.stringify([...ignored]));
      },
    },
    prose: {
      snapshot: () => documentFromEditor(editor),
      restore: (document) => { renderEditorDocument(document, editor); changed(); },
      replaceIn: (blockId, before, after) => {
        const block = editor.querySelector(`[data-block-id="${CSS.escape(blockId)}"]`);
        if (!block || !replaceText(block, before, after)) return false;
        changed();
        return true;
      },
      reveal: (blockId) => {
        const block = editor.querySelector(`[data-block-id="${CSS.escape(blockId)}"]`);
        if (block) { block.scrollIntoView({ block: "center" }); block.focus(); }
      },
    },
  });

  // The panel renders itself; this only decides whether the tab is looking.
  const reviewWriting = () => {
    if (context.body.dataset.tab !== "coach") return;
    coach.review();
  };

  context.body.addEventListener("writer:tab", (event) => {
    if (event.detail === "coach") reviewWriting();
    else fill(context.body, [el("p", { class: "muted", text: "Select words in the manuscript to look them up in Akasha." })]);
  });

  const compare = comparisonDialog(drafts, async (leftId, rightId, target) => {
    fill(target, [el("p", { class: "muted", text: "Aligning drafts..." })]);
    try {
      const [left, right] = await Promise.all([
        api.draft(manuscript.book, entry.volume.id, section.id, leftId),
        api.draft(manuscript.book, entry.volume.id, section.id, rightId),
      ]);
      paintComparison(target, left, right, compareDocuments(left.document, right.document));
    } catch (error) {
      fill(target, [el("p", { class: "form-error", text: error.message || "The drafts could not be compared." })]);
    }
  });

  const navigate = async (event) => {
    event.preventDefault();
    await autosave.flush(true);
    if (!autosave.hasPending()) window.location.href = event.currentTarget.href;
  };
  const createChapter = async (volume) => {
    await autosave.flush();
    if (autosave.hasPending()) return;
    const name = await askDraftName("Name the new chapter", "Untitled chapter");
    if (!name) return;
    const sectionId = availableId(
      name, new Set(volume.sections.map((item) => item.id)), "chapter",
    );
    await api.createSection(manuscript.book, volume.id, sectionId, {
      kind: "chapter", title: name, overview: "", event_ids: [], document: emptyDocument(),
    });
    window.location.href = writerUrl(base, manuscript.book, volume.id, sectionId);
  };
  const toolbar = el("div", { class: "writer-format", role: "toolbar", "aria-label": "Formatting" }, [
    formatButton("Undo", "undo"), formatButton("Redo", "redo"),
    formatButton("B", "bold", "Bold"), formatButton("I", "italic", "Italic"),
    formatButton("S", "strikeThrough", "Strikethrough"),
    formatButton("Bullets", "insertUnorderedList"), formatButton("Numbered", "insertOrderedList"),
    el("select", { class: "writer-block-style", "aria-label": "Block style",
      onchange: (event) => { document.execCommand("formatBlock", false, event.target.value); editor.focus(); changed(); } }, [
      el("option", { value: "p", text: "Paragraph" }),
      el("option", { value: "h2", text: "Heading 1" }),
      el("option", { value: "h3", text: "Heading 2" }),
      el("option", { value: "h4", text: "Heading 3" }),
    ]),
  ]);

  const shell = el("div", { class: "writer-shell" }, [
    el("header", { class: "writer-topbar" }, [
      el("button", { class: "writer-mobile-button", type: "button", text: "Outline",
        onclick: () => document.body.classList.toggle("show-writer-outline") }),
      el("a", { class: "writer-back", href: `${base}/?${new URLSearchParams({ book: manuscript.book })}`,
        text: `${entry.volume.title} / ${sectionName(section)}`, onclick: navigate }),
      draftSelect, primaryBadge,
      el("button", { class: "btn ghost sm", type: "button", text: "New draft", onclick: async () => {
        const name = await askDraftName("Name the new draft", `Draft ${drafts.length + 1}`);
        if (!name) return;
        await autosave.flush();
        if (autosave.hasPending()) return;
        const created = await api.createDraft(
          manuscript.book, entry.volume.id, section.id,
          { name, source: draft.id },
        );
        window.location.href = writerUrl(base, manuscript.book, entry.volume.id, section.id, created.id);
      } }),
      el("button", { class: "btn ghost sm", type: "button", text: "Rename", onclick: async () => {
        const name = await askDraftName("Rename draft", draft.name);
        if (!name || name === draft.name) return;
        draft.name = name;
        // `draft` and its row in `drafts` are separate reads, and the selector
        // renders from the rows -- without this the new name only appeared
        // once autosave came back.
        const row = drafts.find((item) => item.id === draft.id);
        if (row) row.name = name;
        renderDraftOptions();
        changed();
      } }),
      el("button", { class: "btn ghost sm", type: "button", text: "Make primary", onclick: async () => {
        await autosave.flush();
        if (autosave.hasPending() || draft.primary) return;
        const result = await api.makePrimary(
          manuscript.book, entry.volume.id, section.id, draft.id, sectionRev,
        );
        sectionRev = result.section_rev;
        drafts.forEach((item) => { item.primary = item.id === draft.id; });
        draft.primary = true;
        renderDraftOptions();
      } }),
      el("button", { class: "btn ghost sm", type: "button", text: "Compare", disabled: drafts.length < 2,
        onclick: async () => {
          await autosave.flush();
          if (!autosave.hasPending()) compare.showModal();
        } }),
      count, status, conflictAction,
      el("button", { class: "writer-mobile-button", type: "button", text: "Tools",
        onclick: () => document.body.classList.toggle("show-writer-context") }),
      el("button", { class: "btn sm", type: "button", text: "Done", onclick: async () => {
        await autosave.flush(true);
        if (!autosave.hasPending()) onDone(editor.querySelector("[data-block-id]")?.dataset.blockId || null);
      } }),
    ]),
    el("div", { class: "writer-columns" }, [
      outline(manuscript, entry, base, navigate, createChapter),
      el("main", { class: "writer-page" }, [
        el("p", { class: "eyebrow", text: `Volume ${entry.volume.number} / ${sectionLabel(section)}` }),
        title,
        toolbar,
        editor,
      ]),
      context.node,
    ]),
  ]);
  fill(container, [shell]);
  renderDraftOptions();
  renderEditorDocument(draft.document, editor);
  const recovered = await recovery.get(key).catch(() => null);
  let resumedCaret = null;
  if (recovered && recovered.document) {
    renderEditorDocument(recovered.document, editor);
    title.value = recovered.title || title.value;
    resumedCaret = recovered.caret || null;
    if (recovered.draftRev === draft.rev) autosave.schedule(recovered);
    else setStatus("conflict");
  }
  updateCount();
  fill(context.body, [el("p", { class: "muted", text: "Select words in the manuscript to look them up in Akasha." })]);

  editor.addEventListener("input", changed);
  editor.addEventListener("click", (event) => {
    const mention = mentionAt(event.target, editor);
    if (mention) showMentionPanel(mention);
  });
  editor.addEventListener("keydown", (event) => {
    if (!(event.metaKey || event.ctrlKey)) return;
    if (event.key.toLowerCase() === "s") {
      event.preventDefault();
      autosave.flush(false);
    }
    if (event.key.toLowerCase() === "k") {
      const found = selectedProse(editor, window.getSelection());
      if (!found) return;
      event.preventDefault();
      selection = found;
      showAkashaPrompt();
    }
  });
  title.addEventListener("input", changed);
  editor.addEventListener("contextmenu", openContextMenu);
  document.addEventListener("mousedown", (event) => {
    if (!contextMenu.hidden && !contextMenu.contains(event.target)) closeContextMenu();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !contextMenu.hidden) {
      closeContextMenu();
      editor.focus({ preventScroll: true });
    }
  });
  window.addEventListener("scroll", closeContextMenu, true);
  window.addEventListener("resize", closeContextMenu);
  draftSelect.addEventListener("change", async () => {
    await autosave.flush(true);
    if (autosave.hasPending()) { draftSelect.value = draft.id; return; }
    window.location.href = writerUrl(
      base, manuscript.book, entry.volume.id, section.id, draftSelect.value,
    );
  });
  conflictAction.addEventListener("click", async () => {
    const held = snapshot();
    const created = await api.createDraft(
      manuscript.book, entry.volume.id, section.id,
      { name: `Recovered ${new Date().toLocaleString()}`, source: draft.id },
    );
    const saved = await api.saveDraft(
      manuscript.book, entry.volume.id, section.id, created.id,
      { name: created.name, document: held.document }, created.rev,
    );
    await recovery.remove(key).catch(() => {});
    window.location.href = writerUrl(base, manuscript.book, entry.volume.id, section.id, saved.id);
  });
  window.addEventListener("pagehide", () => autosave.flush(true), { once: true });
  window.addEventListener("online", () => autosave.flush(false));
  if (window.visualViewport) {
    const placeToolbar = () => {
      const covered = Math.max(
        0, window.innerHeight - window.visualViewport.height - window.visualViewport.offsetTop,
      );
      toolbar.style.setProperty("--writer-keyboard-offset", `${covered}px`);
    };
    window.visualViewport.addEventListener("resize", placeToolbar);
    window.visualViewport.addEventListener("scroll", placeToolbar);
    placeToolbar();
  }
  // Where to land, best first: exactly where the writer stopped typing, then
  // the block the reader deep-linked, then the top of the draft.
  if (resumedCaret && placeCaret(editor, resumedCaret)) {
    editor.focus({ preventScroll: true });
    return;
  }
  const requestedBlock = new URLSearchParams(window.location.search).get("block");
  const focusBlock = requestedBlock
    ? editor.querySelector(`[data-block-id="${CSS.escape(requestedBlock)}"]`) : editor;
  if (focusBlock) {
    focusBlock.scrollIntoView({ block: "center" });
    editor.focus({ preventScroll: true });
    if (focusBlock !== editor) {
      const caret = document.createRange();
      caret.selectNodeContents(focusBlock);
      caret.collapse(false);
      const browserSelection = window.getSelection();
      browserSelection.removeAllRanges();
      browserSelection.addRange(caret);
    }
  }
}
