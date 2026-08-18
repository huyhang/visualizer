// The goal form: write a new goal, or change an existing one. One form for
// both, because they ask the same four questions — only the id (permanent) and
// the verb differ. A modal, like the book form and the plotline editor: editing
// a goal is a detour from reading the diagram, and cancelling should leave the
// diagram exactly as it was.
//
// Two of the four fields are the reason goals exist as records at all.
// `depends_on` is what makes them a graph rather than a list of labels, and
// `achieved_at` is the single point where a goal touches the timeline — with it,
// chronos can say whether the story delivers the goal, and in an order that
// holds. Both are pickers over what the book already has, because both are
// references the server will refuse if they name nothing.

import { api } from "./api.js";
import { clear, el, field, toast } from "./dom.js";
import { confirmModal, modal, suggestBox } from "./picker.js";
import { slugify } from "./shared/slug.js";

// `goal` is a goal response to edit, or null to create one. `goals` is the rest
// of the book's goals, for the dependency picker. onDone fires after a
// successful write, onDeleted after the goal is gone — the caller decides where
// the writer lands, because it is the thing that knows where they were.
export function openGoalForm(book, goal = null, { goals = [], onDone, onDeleted } = {}) {
  const editing = goal !== null;
  const state = {
    id: editing ? goal.id : "",
    title: editing ? (goal.title || "") : "",
    description: editing ? (goal.description || "") : "",
    dependsOn: editing ? [...goal.depends_on] : [],
    achievedAt: editing ? goal.achieved_at : null,
    // Shown beside the id; the picker knows the title, the payload does not.
    achievedTitle: editing && goal.achieved_scene ? goal.achieved_scene.title : null,
  };
  // Never itself, and never a goal that already depends on this one — the
  // server refuses both as loops, and offering them would be an invitation to
  // be told no. Only the direct dependents are excluded here; a deeper loop is
  // rare enough to leave to the server, which checks the whole chain.
  const dependents = new Set(
    goals.filter((g) => (g.depends_on || []).includes(state.id)).map((g) => g.id)
  );
  const offerable = goals.filter((g) => g.id !== state.id && !dependents.has(g.id));

  let idTouched = editing;

  const titleBox = el("input", {
    type: "text", value: state.title, autocomplete: "off",
    placeholder: "Deliver the Ember Seal",
  });
  const idBox = el("input", {
    type: "text", value: state.id, autocomplete: "off",
    placeholder: "deliver-the-ember-seal", disabled: editing ? "" : null,
  });
  const descriptionBox = el("textarea", {
    rows: "3", text: state.description,
    placeholder: "What this goal is, in your own words.",
  });
  const error = el("p", { class: "form-error", hidden: "" });
  const submit = el("button", {
    class: "btn", type: "button", text: editing ? "Save" : "Create goal",
  });

  // An id derived from the title as it is typed, until the writer edits it
  // themselves — the same bargain the book form strikes. Ids are permanent, so
  // this only ever runs while creating.
  titleBox.addEventListener("input", () => {
    state.title = titleBox.value;
    if (!idTouched) {
      state.id = slugify(state.title);
      idBox.value = state.id;
    }
    refresh();
  });
  idBox.addEventListener("input", () => {
    idTouched = true;
    state.id = idBox.value.trim();
    refresh();
  });
  descriptionBox.addEventListener("input", () => { state.description = descriptionBox.value; });

  const dependencies = el("div", { class: "chip-row goal-deps" });
  const achieved = el("div", { class: "goal-achieved" });

  function renderDependencies() {
    clear(dependencies);
    if (!state.dependsOn.length) {
      dependencies.appendChild(el("span", { class: "muted", text: "Rests on nothing." }));
    }
    for (const id of state.dependsOn) {
      const named = goals.find((g) => g.id === id);
      dependencies.appendChild(el("span", { class: "chip goal removable" }, [
        el("span", { text: named ? named.name : id }),
        el("button", {
          class: "ref-remove", type: "button", text: "✕", title: "Remove dependency",
          onclick: () => {
            state.dependsOn = state.dependsOn.filter((g) => g !== id);
            renderDependencies();
          },
        }),
      ]));
    }
  }

  function renderAchieved() {
    clear(achieved);
    if (!state.achievedAt) {
      achieved.appendChild(el("span", { class: "muted", text: "No scene yet." }));
      return;
    }
    achieved.appendChild(el("span", { class: "chip removable" }, [
      el("span", { text: state.achievedTitle || state.achievedAt }),
      el("button", {
        class: "ref-remove", type: "button", text: "✕", title: "Clear the scene",
        onclick: () => {
          state.achievedAt = null;
          state.achievedTitle = null;
          renderAchieved();
        },
      }),
    ]));
  }

  // Filtered in the browser: the book's goals are already in hand (the diagram
  // needs them all), so asking the server to search a list of thirty would be a
  // round trip for nothing.
  const dependencyPicker = suggestBox({
    placeholder: "Add a prerequisite…",
    search: (query) => {
      const words = query.toLowerCase().split(/\s+/).filter(Boolean);
      return offerable.filter((g) =>
        !state.dependsOn.includes(g.id)
        && words.every((w) => `${g.name} ${g.id}`.toLowerCase().includes(w))
      );
    },
    renderItem: (g) => [
      el("span", { class: "suggest-name", text: g.name }),
      el("span", { class: "suggest-meta muted", text: g.id }),
    ],
    onPick: (g) => {
      state.dependsOn.push(g.id);
      renderDependencies();
      dependencyPicker.refresh();
    },
    empty: "No other goals to rest on.",
  });

  const scenePicker = suggestBox({
    placeholder: "Search this book's scenes…",
    search: async (query) => (await api.listEvents(book, { filter: query, perPage: 8 })).events,
    renderItem: (e) => [
      el("span", { class: "suggest-name", text: e.title }),
      el("span", { class: "suggest-meta muted", text: e.when }),
    ],
    onPick: (e) => {
      state.achievedAt = e.id;
      state.achievedTitle = e.title;
      renderAchieved();
    },
  });

  function body() {
    return {
      title: state.title.trim() || null,
      description: state.description,
      depends_on: state.dependsOn,
      achieved_at: state.achievedAt,
    };
  }

  async function save() {
    error.hidden = true;
    submit.disabled = true;
    try {
      const saved = editing
        ? await api.updateGoal(book, state.id, body(), goal.rev)
        : await api.createGoal(book, state.id, body());
      dialog.close();
      toast(editing ? "Goal updated." : `Created “${saved.name}”.`);
      if (onDone) onDone(saved);
    } catch (e) {
      error.textContent = failure(e);
      error.hidden = false;
      submit.disabled = false;
    }
  }

  // Deleting a goal is refused while threads serve it or other goals rest on
  // it, and the refusal names them — so the confirmation is built from the
  // server's own answer rather than from a guess made before asking.
  function confirmDelete() {
    const serving = (goal.plotlines || []).map((p) => p.title);
    const resting = (goal.required_by || []).map((g) => g.title);
    if (!serving.length && !resting.length) {
      confirmModal(`Delete “${goal.name}”?`, "Nothing points at it.",
        { yes: "Delete", danger: true, onYes: () => doDelete(false) });
      return;
    }
    confirmModal(`Delete “${goal.name}”?`, el("div", {}, [
      el("p", { text: "This goal is still pointed at:" }),
      el("ul", { class: "plain-list" }, [
        ...serving.map((t) => el("li", { text: `${t} — a thread serving it` })),
        ...resting.map((t) => el("li", { text: `${t} — a goal resting on it` })),
      ]),
      el("p", { class: "muted", text:
        "Deleting removes it from each of them. Their own scenes and prose are "
        + "untouched." }),
    ]), { yes: "Delete anyway", danger: true, onYes: () => doDelete(true) });
  }

  async function doDelete(detach) {
    try {
      await api.deleteGoal(book, goal.id, goal.rev, { detach });
    } catch (e) {
      error.textContent = failure(e);
      error.hidden = false;
      return;
    }
    dialog.close();
    toast(`Deleted “${goal.name}”.`);
    if (onDeleted) onDeleted(goal.id);
  }

  function failure(e) {
    if (e.code === "ALREADY_EXISTS") {
      return `A goal with the id “${state.id}” already exists. Choose another.`;
    }
    if (e.code === "GOAL_CYCLE") {
      const cycle = (e.evidence.cycle || []).join(" → ");
      return `That would make the goals loop: ${cycle}.`;
    }
    if (e.isConflict) {
      return "Someone else changed this goal — reload the page before saving.";
    }
    return e.message || "Could not save the goal.";
  }

  function refresh() {
    submit.disabled = !state.id;
  }

  const dialog = modal(editing ? `Edit “${goal.name}”` : "New goal", el("div", {}, [
    field("Name", titleBox),
    field("Id", idBox, editing
      ? "An id is permanent — it is what threads and other goals point at."
      : "Derived from the name; edit it before creating if you want another."),
    field("What it is", descriptionBox),
    field("Rests on", el("div", {}, [dependencies, dependencyPicker.el]),
      "Goals that must be met before this one."),
    field("Achieved at", el("div", {}, [achieved, scenePicker.el]),
      "The scene that delivers it. Leave it empty until you have written one."),
    error,
    el("div", { class: "form-actions" }, [
      submit,
      el("button", { class: "btn secondary", type: "button", text: "Cancel",
        onclick: () => dialog.close() }),
      editing
        ? el("button", { class: "btn danger ghost", type: "button", text: "Delete",
            onclick: confirmDelete })
        : null,
    ].filter(Boolean)),
  ]));

  submit.addEventListener("click", save);
  renderDependencies();
  renderAchieved();
  refresh();
  return dialog;
}
