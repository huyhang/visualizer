// Content-page mutations. State and I/O arrive through this factory so the
// reader remains responsible only for rendering the outline around it.

import {
  allSectionIds,
  availableId,
  beforeForPosition,
  emptyDocument,
  moveBefore,
  moveFailure,
  sameOrder,
  sectionKindChoices,
  singletonConflict,
} from "./contents.js";
import { el, fill } from "./dom.js";
import { sectionName } from "./navigation.js";
import { createTouchDrag } from "./touchdrag.js";

const option = (value, text, selected = false, disabled = false) =>
  el("option", { value, text, selected, disabled });

const KIND_LABELS = {
  chapter: "Chapter",
  prologue: "Prologue",
  epilogue: "Epilogue",
  glossary: "Glossary",
};

export function createContentManager({
  api, base, elements, editorUrl, navigate, render, showError, showRetry,
}) {
  const {
    content,
    volumeDialog,
    volumeForm,
    volumeName,
    volumeOverview,
    volumeError,
    renameDialog,
    renameForm,
    renameName,
    renameOverview,
    renameError,
    sectionDialog,
    sectionForm,
    sectionTitle,
    sectionVolume,
    sectionKind,
    sectionError,
    moveDialog,
    moveForm,
    moveTitle,
    moveVolume,
    movePosition,
    moveError,
    closeButtons,
  } = elements;
  let manuscript = null;
  let moving = null;
  let renaming = null;
  let dragged = null;
  let preferredVolume = null;

  function setManuscript(value) {
    manuscript = value;
  }

  function reset() {
    manuscript = null;
    moving = null;
    renaming = null;
    dragged = null;
    preferredVolume = null;
    // Leaving the book mid-gesture must not strand a captured pointer.
    touchDrag.release();
  }

  function openVolumeCreator(value) {
    setManuscript(value);
    volumeForm.reset();
    volumeError.textContent = "";
    volumeDialog.showModal();
    volumeName.focus();
  }

  async function createVolume() {
    if (!manuscript) return;
    const title = volumeName.value.trim();
    if (!title) return;
    const known = new Set(manuscript.volumes.map((volume) => volume.id));
    const id = availableId(title, known, "volume");
    volumeError.textContent = "Creating…";
    try {
      const created = await api.createVolume(manuscript.book, id, {
        title,
        overview: volumeOverview.value.trim(),
      });
      const updated = await api.manuscript(manuscript.book);
      preferredVolume = created.id;
      volumeDialog.close();
      render(updated, `${title} was created.`);
    } catch (error) {
      volumeError.textContent = error.message || "The volume could not be created.";
    }
  }

  function openSectionCreator(value, selectedVolume = null) {
    setManuscript(value);
    sectionForm.reset();
    fill(sectionVolume, manuscript.volumes.map((volume) => option(
      volume.id,
      `Volume ${volume.number} · ${volume.title}`,
      volume.id === selectedVolume,
    )));
    if (selectedVolume) sectionVolume.value = selectedVolume;
    paintKinds();
    sectionError.textContent = "";
    sectionDialog.showModal();
    sectionTitle.focus();
  }

  /**
   * Every kind, with the ones this volume already has shown as unavailable.
   *
   * Disabled rather than absent: a menu that quietly drops "Prologue" looks
   * broken, where one that greys it out and says why explains the rule.
   */
  function paintKinds() {
    if (!manuscript) return;
    const volume = volumeById(sectionVolume.value);
    const choices = sectionKindChoices(volume);
    const usable = choices.filter((choice) => choice.available)
      .map((choice) => choice.kind);
    const wanted = usable.includes(sectionKind.value)
      ? sectionKind.value
      : usable[0];
    fill(sectionKind, choices.map((choice) => option(
      choice.kind,
      choice.available
        ? KIND_LABELS[choice.kind]
        : `${KIND_LABELS[choice.kind]} — already in ${volume.title}`,
      choice.kind === wanted,
      !choice.available,
    )));
    sectionKind.value = wanted;
  }

  function volumeById(volumeId) {
    return (manuscript?.volumes || []).find(
      (candidate) => candidate.id === volumeId,
    );
  }

  async function createSection() {
    if (!manuscript) return;
    const title = sectionTitle.value.trim();
    const volume = volumeById(sectionVolume.value);
    const kind = sectionKind.value || "chapter";
    if (!title || !volume) return;
    const section = availableId(title, allSectionIds(manuscript), kind);
    sectionError.textContent = "Creating…";
    try {
      await api.createSection(manuscript.book, volume.id, section, {
        kind,
        title,
        overview: "",
        event_ids: [],
        document: emptyDocument(),
      });
      navigate(editorUrl(base, manuscript.book, volume.id, section));
    } catch (error) {
      sectionError.textContent = error.message
        || `The ${KIND_LABELS[kind].toLowerCase()} could not be created.`;
    }
  }

  function openVolumeRenamer(value, volumeId) {
    setManuscript(value);
    const volume = volumeById(volumeId);
    if (!volume) return;
    renaming = volume;
    renameForm.reset();
    renameName.value = volume.title || "";
    renameOverview.value = volume.overview || "";
    renameError.textContent = "";
    renameDialog.showModal();
    renameName.select();
  }

  async function renameVolume() {
    if (!manuscript || !renaming) return;
    const title = renameName.value.trim();
    if (!title) return;
    renameError.textContent = "Saving…";
    try {
      await api.updateVolume(
        manuscript.book,
        renaming.id,
        { title, overview: renameOverview.value.trim() },
        renaming.rev,
      );
      preferredVolume = renaming.id;
      renameDialog.close();
      render(await api.manuscript(manuscript.book), `${title} was renamed.`);
    } catch (error) {
      renameError.textContent = error.message
        || "The volume could not be renamed.";
    }
  }

  function paintMovePositions() {
    if (!manuscript || !moving) return;
    const target = manuscript.volumes.find(
      (volume) => volume.id === moveVolume.value,
    );
    if (!target) return;
    fill(movePosition, [
      option("start", "At the beginning"),
      ...target.sections.map((section) => option(
        `after:${section.id}`, `After ${sectionName(section)}`,
      )),
      option("end", "At the end", true),
    ]);
  }

  function openSectionMover(value, volume, section) {
    setManuscript(value);
    moving = { volume, section };
    moveTitle.textContent = `Move ${sectionName(section)}`;
    fill(moveVolume, manuscript.volumes
      .filter((candidate) => candidate.id !== volume.id)
      .map((candidate) => option(
        candidate.id, `Volume ${candidate.number} · ${candidate.title}`,
      )));
    moveError.textContent = "";
    paintMovePositions();
    moveDialog.showModal();
    moveVolume.focus();
  }

  async function submitSectionMove() {
    if (!manuscript || !moving) return;
    const target = manuscript.volumes.find(
      (volume) => volume.id === moveVolume.value,
    );
    if (!target) return;
    const conflict = singletonConflict(moving.section, target);
    if (conflict) {
      moveError.textContent = `${target.title} already has a ${moving.section.kind}.`;
      return;
    }
    const selected = movePosition.value;
    const position = selected.startsWith("after:") ? selected.slice(6) : selected;
    const before = beforeForPosition(target.sections, position);
    moveError.textContent = "Moving…";
    try {
      const updated = await api.moveSection(
        manuscript.book,
        moving.volume.id,
        moving.section.id,
        target.id,
        before,
        moving.section.rev,
      );
      preferredVolume = target.id;
      moveDialog.close();
      render(updated, `${sectionName(moving.section)} was moved.`);
    } catch (error) {
      if (await showPendingMove(error, manuscript, {
        source_volume: moving.volume.id,
        target_volume: target.id,
        section: moving.section.id,
        before,
        section_rev: moving.section.rev,
        title: moving.section.title,
      })) {
        moveDialog.close();
      } else {
        moveError.textContent = error.message || "The section could not be moved.";
      }
    }
  }

  function setSaving(saving) {
    content.toggleAttribute("aria-busy", saving);
    const status = content.querySelector("#contents-save-status");
    if (status) status.textContent = saving ? "Saving…" : "";
  }

  async function reorderVolume(value, volumeId, before) {
    const current = value.volumes.map((volume) => volume.id);
    const reordered = moveBefore(current, volumeId, before);
    if (sameOrder(current, reordered)) return;
    setSaving(true);
    try {
      render(
        await api.reorderVolumes(value.book, reordered, value.rev),
        "Volume order updated.",
      );
    } catch (error) {
      reportFailure(
        error,
        "The volumes could not be reordered",
        () => retryAfterRefresh(
          value.book, (fresh) => reorderVolume(fresh, volumeId, before),
        ),
      );
    } finally {
      setSaving(false);
    }
  }

  /**
   * Say what went wrong, and offer a way out only when there is one.
   *
   * A refusal is final however often it is repeated, so it gets a plain notice
   * naming the reason. Anything that might have landed halfway gets a notice
   * that stays put with a Retry beside it -- the way out must not vanish
   * before it has been read.
   */
  function reportFailure(error, what, retry) {
    const failure = moveFailure(error);
    if (!failure.retriable) {
      showError(`${what}: ${error.message || "the server declined it."}`);
      return;
    }
    showRetry(`${what} because ${failure.detail}. Retry to finish it.`, retry);
  }

  /** Reload before retrying, so a stale revision cannot fail the attempt twice. */
  async function retryAfterRefresh(book, attempt) {
    let fresh;
    try {
      fresh = await api.manuscript(book);
    } catch (error) {
      showRetry(
        "The outline could not be reloaded. Retry when the connection is back.",
        () => retryAfterRefresh(book, attempt),
      );
      return;
    }
    setManuscript(fresh);
    await attempt(fresh);
  }

  /** Where a section lands: a reorder at home, or a move to another volume. */
  async function placeSection(value, source, section, target, before) {
    if (source.id === target.id) {
      await reorderWithin(value, source, section, before);
      return;
    }
    const conflict = singletonConflict(section, target);
    if (conflict) {
      showError(`${target.title} already has a ${section.kind}.`);
      return;
    }
    setSaving(true);
    try {
      const updated = await api.moveSection(
        value.book, source.id, section.id, target.id, before, section.rev,
      );
      preferredVolume = target.id;
      render(updated, `${sectionName(section)} was moved.`);
    } catch (error) {
      if (!(await showPendingMove(error, value, {
        source_volume: source.id,
        target_volume: target.id,
        section: section.id,
        before,
        section_rev: section.rev,
        title: section.title,
      }))) {
        showError(error.message || "The section could not be moved.");
      }
    } finally {
      setSaving(false);
    }
  }

  /** A reorder inside one volume: the whole order is rewritten, nothing moves. */
  async function reorderWithin(value, source, section, before) {
    const current = source.sections.map((candidate) => candidate.id);
    const reordered = moveBefore(current, section.id, before);
    if (sameOrder(current, reordered)) return;
    setSaving(true);
    try {
      await api.reorderSections(value.book, source.id, reordered, source.rev);
      render(await api.manuscript(value.book), "Section order updated.");
    } catch (error) {
      reportFailure(
        error,
        "The sections could not be reordered",
        () => retryAfterRefresh(
          value.book, (fresh) => retryReorder(fresh, source.id, section.id, before),
        ),
      );
    } finally {
      setSaving(false);
    }
  }

  /** Re-attempt a reorder against a freshly read outline, if it still applies. */
  function retryReorder(fresh, volumeId, sectionId, before) {
    const home = fresh.volumes.find((volume) => volume.id === volumeId);
    const still = home?.sections.find((row) => row.id === sectionId);
    if (!home || !still) {
      showError("That section is no longer in the outline.");
      return undefined;
    }
    return placeSection(fresh, home, still, home, before);
  }

  async function showPendingMove(error, value, requested) {
    // A refusal changed nothing, so there is no partial state to reconcile and
    // the caller should just say why. Everything else may have landed halfway.
    if (!moveFailure(error).retriable) return false;
    try {
      const updated = await api.manuscript(value.book);
      const pending = (updated.pending_section_moves || []).length > 0;
      const completed = (updated.section_aliases || []).some((alias) =>
        alias.source_volume === requested.source_volume
          && alias.target_volume === requested.target_volume
          && alias.section === requested.section,
      );
      render(
        updated,
        pending ? null : completed
          ? "The move completed."
          : "The move did not start. Please try it again.",
      );
      return true;
    } catch (_refreshError) {
      showLocalRecovery(value, requested);
      return true;
    }
  }

  function showLocalRecovery(value, requested) {
    content.querySelector(".move-warning.local")?.remove();
    const status = el("span", {
      class: "move-warning-status",
      role: "status",
      "aria-live": "polite",
    });
    const warning = el("section", {
      class: "reader-notice move-warning local", role: "alert",
    }, [
      el("span", { class: "move-warning-copy" }, [
        el("strong", { text: "Move connection lost" }),
        el("span", {
          text: `${requested.title || requested.section} may not have finished moving. `
            + "Your writing is safe; reconnect and finish the move.",
        }),
        status,
      ]),
      el("button", {
        class: "btn sm", type: "button", text: "Retry move",
        onclick: async (event) => {
          event.currentTarget.disabled = true;
          await finishPendingMove(value, requested, status);
          if (event.currentTarget.isConnected) event.currentTarget.disabled = false;
        },
      }),
    ]);
    content.prepend(warning);
  }

  async function finishPendingMove(value, pending, status) {
    status.textContent = "Finishing move…";
    try {
      const updated = await api.moveSection(
        value.book,
        pending.source_volume,
        pending.section,
        pending.target_volume,
        pending.before ?? null,
        pending.section_rev,
      );
      preferredVolume = pending.target_volume;
      render(updated, "The interrupted move was completed.");
    } catch (error) {
      status.textContent = "Still incomplete. Your writing is safe; retry when ready. "
        + (error.message || "The move could not be completed.");
    }
  }

  function startDrag(event, payload) {
    dragged = payload;
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", `${payload.type}:${payload.id}`);
    event.currentTarget.closest(".section-row, .volume-card")
      ?.classList.add("dragging");
  }

  function finishDrag(event) {
    dragged = null;
    event.currentTarget.closest(".section-row, .volume-card")
      ?.classList.remove("dragging");
    content.querySelectorAll(".drop-target").forEach(
      (node) => node.classList.remove("drop-target"),
    );
  }

  function acceptDrop(event, type) {
    if (!dragged || dragged.type !== type) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
    event.currentTarget.classList.add("drop-target");
  }

  function leaveDrop(event) {
    if (!event.currentTarget.contains(event.relatedTarget)) {
      event.currentTarget.classList.remove("drop-target");
    }
  }

  function takeDragged(type) {
    if (!dragged || dragged.type !== type) return null;
    const held = dragged;
    dragged = null;
    return held;
  }

  // -- touch dragging --------------------------------------------------------

  /** The rendered outline as geometry: volumes, and the rows inside them. */
  function dropZones() {
    return [...content.querySelectorAll(".volume-card[data-volume]")].map((card) => {
      const box = card.getBoundingClientRect();
      const rows = [...card.querySelectorAll(".section-row[data-section]")];
      return {
        volume: card.dataset.volume,
        top: box.top,
        bottom: box.bottom,
        sections: rows.map((row) => {
          const rect = row.getBoundingClientRect();
          return { id: row.dataset.section, top: rect.top, bottom: rect.bottom };
        }),
      };
    });
  }

  const touchDrag = createTouchDrag({
    zones: dropZones,
    onSection: (payload, volumeId, before) => {
      const target = volumeById(volumeId);
      if (!manuscript || !target) return;
      placeSection(manuscript, payload.volume, payload.section, target, before);
    },
    onVolume: (payload, before) => {
      if (!manuscript) return;
      reorderVolume(manuscript, payload.id, before);
    },
  });

  function beginTouchDrag(event, payload) {
    touchDrag.begin(event, payload);
  }

  function wire() {
    closeButtons.forEach((button) => {
      button.addEventListener("click", () => button.closest("dialog").close());
    });
    volumeForm.addEventListener("submit", (event) => {
      event.preventDefault();
      createVolume();
    });
    renameForm.addEventListener("submit", (event) => {
      event.preventDefault();
      renameVolume();
    });
    sectionForm.addEventListener("submit", (event) => {
      event.preventDefault();
      createSection();
    });
    sectionVolume.addEventListener("change", paintKinds);
    moveVolume.addEventListener("change", paintMovePositions);
    moveForm.addEventListener("submit", (event) => {
      event.preventDefault();
      submitSectionMove();
    });
  }

  return {
    acceptDrop,
    beginTouchDrag,
    finishDrag,
    finishPendingMove,
    leaveDrop,
    openSectionCreator,
    openSectionMover,
    openVolumeCreator,
    openVolumeRenamer,
    placeSection,
    preferredVolume: () => preferredVolume,
    reorderVolume,
    reset,
    setManuscript,
    startDrag,
    takeDragged,
    wire,
  };
}
