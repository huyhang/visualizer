// The authoring workspace. It owns UI orchestration; document conversion,
// comparison and recovery stay in small injected/pure modules beside it.

import { api } from "./api.js";
import { compareDocuments } from "./comparison.js";
import { el, fill } from "./dom.js";
import {
  documentFromEditor,
  linkMention,
  renderEditorDocument,
  selectedProse,
  wordCount,
} from "./editor.js";
import { createAutosave, createRecoveryStore, recoveryKey } from "./recovery.js";
import { sectionLabel, sectionName } from "./navigation.js";

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

function outline(manuscript, current, base, navigate, createChapter) {
  return el("nav", { class: "writer-outline", "aria-label": "Manuscript outline" }, [
    el("div", { class: "writer-panel-head" }, [
      el("strong", { text: "Outline" }),
      el("button", { class: "writer-panel-close", type: "button", text: "x",
        "aria-label": "Close outline", onclick: () => document.body.classList.remove("show-writer-outline") }),
    ]),
    ...manuscript.volumes.map((volume) => el("section", { class: "writer-volume" }, [
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
      el("button", { class: "new-chapter", type: "button", text: "+ New chapter",
        onclick: () => createChapter(volume) }),
    ])),
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

function paintComparison(target, left, right, compared) {
  const stats = (value) => `${value.words} words | ${value.paragraphs} paragraphs | ${value.averageSentenceWords} words/sentence`;
  fill(target, [
    el("div", { class: "compare-stats" }, [
      el("span", { text: `${left.name}: ${stats(compared.left)}` }),
      el("span", { text: `${right.name}: ${stats(compared.right)}` }),
    ]),
    el("div", { class: "compare-grid" }, compared.rows.flatMap((row) => [
      el("p", { class: `compare-block ${row.status}`, text: row.left || "(not present)" }),
      el("p", { class: `compare-block ${row.status}`, text: row.right || "(not present)" }),
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
  const selectionMenu = el("div", { class: "selection-menu", hidden: true }, [
    el("button", { type: "button", text: "Look up in Akasha" }),
  ]);
  document.body.appendChild(selectionMenu);

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
        entity.preview ? el("p", { text: entity.preview }) : null,
        el("div", { class: "entity-actions" }, [
          el("button", {
            class: "btn sm", type: "button", text: "Link mention",
            disabled: !selection.block,
            title: selection.block ? "Keep this selection linked to Akasha" : "Select within one paragraph to link",
            onclick: () => {
              if (linkMention(selection, entity)) changed();
              selectionMenu.hidden = true;
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
  selectionMenu.firstChild.addEventListener("mousedown", (event) => event.preventDefault());
  selectionMenu.firstChild.addEventListener("click", showAkashaPrompt);

  const showSelectionMenu = () => {
    const found = selectedProse(editor, window.getSelection());
    if (!found) { selectionMenu.hidden = true; return; }
    selection = found;
    const rect = found.range.getBoundingClientRect();
    selectionMenu.style.left = `${Math.max(8, Math.min(rect.left, window.innerWidth - 180))}px`;
    selectionMenu.style.top = `${Math.max(8, rect.top - 42)}px`;
    selectionMenu.hidden = false;
  };

  async function reviewWriting() {
    if (context.body.dataset.tab !== "coach") return;
    fill(context.body, [el("p", { class: "muted", text: "Reviewing locally..." })]);
    try {
      const result = await api.writingReview(
        manuscript.book, documentFromEditor(editor), dialect,
      );
      const dialectPicker = el("label", { class: "coach-dialect" }, [
        el("span", { text: "English" }),
        el("select", { onchange: (event) => {
          dialect = event.target.value;
          try { localStorage.setItem(dialectKey, dialect); } catch (_error) { /* optional */ }
          reviewWriting();
        } }, [
          el("option", { value: "en-US", text: "US", selected: dialect === "en-US" }),
          el("option", { value: "en-GB", text: "UK", selected: dialect === "en-GB" }),
        ]),
      ]);
      const issues = result.issues.filter((issue) => !ignored.has(issue.title));
      if (!issues.length) {
        fill(context.body, [dialectPicker, el("p", { class: "coach-clear", text: "No local suggestions. Keep writing." })]);
        return;
      }
      fill(context.body, [dialectPicker, ...issues.map((issue) => {
        const card = el("article", { class: "coach-issue" });
        fill(card, [
        el("small", { text: issue.category }),
        el("strong", { text: issue.title }),
        el("p", { text: issue.message }),
        el("q", { text: issue.excerpt }),
        el("div", { class: "coach-actions" }, [
          issue.replacement !== null ? el("button", {
            class: "btn sm", type: "button", text: `Use “${issue.replacement}”`,
            onclick: () => {
              const block = editor.querySelector(`[data-block-id="${CSS.escape(issue.block)}"]`);
              const before = documentFromEditor(editor);
              if (block && replaceText(block, issue.excerpt, issue.replacement)) {
                changed();
                fill(card, [el("p", { text: "Suggestion applied." }), el("button", {
                  class: "btn ghost sm", type: "button", text: "Undo",
                  onclick: () => { renderEditorDocument(before, editor); changed(); reviewWriting(); },
                })]);
              }
            },
          }) : null,
          el("button", { class: "btn ghost sm", type: "button", text: "Show",
            onclick: () => {
              const block = editor.querySelector(`[data-block-id="${CSS.escape(issue.block)}"]`);
              if (block) { block.scrollIntoView({ block: "center" }); block.focus(); }
            } }),
          el("button", { class: "btn ghost sm", type: "button", text: "Dismiss",
            onclick: () => card.remove() }),
          el("button", { class: "btn ghost sm", type: "button", text: "Ignore rule",
            onclick: () => {
              ignored.add(issue.title);
              try { localStorage.setItem(ignoredKey, JSON.stringify([...ignored])); } catch (_error) { /* optional */ }
              card.remove();
            } }),
        ]),
        ]);
        return card;
      })]);
    } catch (error) {
      fill(context.body, [el("p", { class: "form-error", text: error.message || "Review failed." })]);
    }
  }

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
  if (recovered && recovered.document) {
    renderEditorDocument(recovered.document, editor);
    title.value = recovered.title || title.value;
    if (recovered.draftRev === draft.rev) autosave.schedule(recovered);
    else setStatus("conflict");
  }
  updateCount();
  fill(context.body, [el("p", { class: "muted", text: "Select words in the manuscript to look them up in Akasha." })]);

  editor.addEventListener("input", changed);
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
  editor.addEventListener("keyup", showSelectionMenu);
  editor.addEventListener("mouseup", showSelectionMenu);
  let selectionTimer = null;
  document.addEventListener("selectionchange", () => {
    clearTimeout(selectionTimer);
    selectionTimer = setTimeout(showSelectionMenu, 80);
  });
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
