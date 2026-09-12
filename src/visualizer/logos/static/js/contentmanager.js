// Content-page mutations. State and I/O arrive through this factory so the
// reader remains responsible only for rendering the outline around it.

import {
  allSectionIds,
  availableId,
  beforeForPosition,
  emptyDocument,
  moveBefore,
  sameOrder,
  singletonConflict,
} from "./contents.js";
import { el, fill } from "./dom.js";
import { sectionName } from "./navigation.js";

const option = (value, text, selected = false) =>
  el("option", { value, text, selected });

export function createContentManager({
  api, base, elements, editorUrl, navigate, render, showError,
}) {
  const {
    content,
    volumeDialog,
    volumeForm,
    volumeName,
    volumeOverview,
    volumeError,
    chapterDialog,
    chapterForm,
    chapterName,
    chapterVolume,
    chapterError,
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
  let dragged = null;
  let preferredVolume = null;

  function setManuscript(value) {
    manuscript = value;
  }

  function reset() {
    manuscript = null;
    moving = null;
    dragged = null;
    preferredVolume = null;
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

  function openChapterCreator(value, selectedVolume = null) {
    setManuscript(value);
    chapterForm.reset();
    fill(chapterVolume, manuscript.volumes.map((volume) => option(
      volume.id,
      `Volume ${volume.number} · ${volume.title}`,
      volume.id === selectedVolume,
    )));
    if (selectedVolume) chapterVolume.value = selectedVolume;
    chapterError.textContent = "";
    chapterDialog.showModal();
    chapterName.focus();
  }

  async function createChapter() {
    if (!manuscript) return;
    const title = chapterName.value.trim();
    const volume = manuscript.volumes.find(
      (candidate) => candidate.id === chapterVolume.value,
    );
    if (!title || !volume) return;
    const section = availableId(title, allSectionIds(manuscript), "chapter");
    chapterError.textContent = "Creating…";
    try {
      await api.createSection(manuscript.book, volume.id, section, {
        kind: "chapter",
        title,
        overview: "",
        event_ids: [],
        document: emptyDocument(),
      });
      navigate(editorUrl(base, manuscript.book, volume.id, section));
    } catch (error) {
      chapterError.textContent = error.message || "The chapter could not be created.";
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
      showError(error.message || "The volumes could not be reordered.");
    } finally {
      setSaving(false);
    }
  }

  async function placeSection(value, source, section, target, before) {
    if (source.id === target.id) {
      const current = source.sections.map((candidate) => candidate.id);
      const reordered = moveBefore(current, section.id, before);
      if (sameOrder(current, reordered)) return;
      setSaving(true);
      try {
        await api.reorderSections(value.book, source.id, reordered, source.rev);
        render(await api.manuscript(value.book), "Section order updated.");
      } catch (error) {
        showError(error.message || "The sections could not be reordered.");
      } finally {
        setSaving(false);
      }
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

  async function showPendingMove(error, value, requested) {
    if (error.status && error.status < 500) return false;
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

  function wire() {
    closeButtons.forEach((button) => {
      button.addEventListener("click", () => button.closest("dialog").close());
    });
    volumeForm.addEventListener("submit", (event) => {
      event.preventDefault();
      createVolume();
    });
    chapterForm.addEventListener("submit", (event) => {
      event.preventDefault();
      createChapter();
    });
    moveVolume.addEventListener("change", paintMovePositions);
    moveForm.addEventListener("submit", (event) => {
      event.preventDefault();
      submitSectionMove();
    });
  }

  return {
    acceptDrop,
    finishDrag,
    finishPendingMove,
    leaveDrop,
    openChapterCreator,
    openSectionMover,
    openVolumeCreator,
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
