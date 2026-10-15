// The writing page, assembled: the outline, the page with its title, formatting
// bar and prose, and the writing tools -- with every note, the Coach's and the
// editor's, underlined in the prose where it belongs.
//
// This component wires; the work is in the hooks it composes:
//   useDraftSession  saving, recovery and the draft actions
//   useWriterEditor  the editor and what it reports
//   useCoach         the local Writing Coach
//   useEditorReview  the editor on the GPU box
//   useNoteActions   accepting and setting aside notes
//   useAkasha        looking words up, and linked phrases

import type { Editor } from "@tiptap/core";
import { EditorContent } from "@tiptap/react";
import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type MouseEvent,
} from "react";
import { messageOf } from "../../api/errors";
import type { Entity } from "../../api/types";
import { pmToLogos } from "../../doc/convert";
import { wordCount } from "../../doc/text";
import type { Placement } from "../../editor/annotations";
import { linkable, mentionAt } from "../../editor/mentions";
import { caretAt, caretPos, findBlock } from "../../editor/positions";
import { useNotify } from "../../../components/ui/Toaster";
import { useDeps } from "../../deps";
import { lookupText, useAkasha } from "../../hooks/useAkasha";
import { useCoach } from "../../hooks/useCoach";
import { useDraftSession, type EditorReader } from "../../hooks/useDraftSession";
import { useDrawerLayout } from "../../hooks/useDrawerLayout";
import { useDrawers } from "../../hooks/useDrawers";
import { useEditorReview } from "../../hooks/useEditorReview";
import { useKeyboardOffset } from "../../hooks/useKeyboardOffset";
import { useLatest } from "../../hooks/useLatest";
import { useNoteActions } from "../../hooks/useNoteActions";
import { useWriterEditor } from "../../hooks/useWriterEditor";
import type { Workspace as Loaded } from "../../hooks/useWorkspace";
import { coachNote, editorNote, type Note } from "../../logic/notes";
import { sectionLabel, sectionName } from "../../logic/outline";
import type { Layers } from "../../logic/preferences";
import {
  coachAnnotations,
  editorAnnotations,
  editorAnnotationId,
} from "../../logic/review";
import type { Panel, Route } from "../../logic/route";
import { EditorTab } from "../review/EditorTab";
import { NotePopover } from "../review/NotePopover";
import type { AskSettings } from "../review/AskOptions";
import { AkashaTab } from "../tools/AkashaTab";
import { CoachTab } from "../tools/CoachTab";
import { ToolsPanel } from "../tools/ToolsPanel";
import { CompareDialog } from "./CompareDialog";
import { ContextMenu, type MenuAction, type MenuRequest } from "./ContextMenu";
import { FormatBar } from "./FormatBar";
import { useNameDialog } from "./NameDialog";
import { OutlinePanel } from "./OutlinePanel";
import { TopBar } from "./TopBar";

const underline = (id: string) =>
  document.querySelector<HTMLElement>(`[data-annotation="${CSS.escape(id)}"]`);

export function Workspace({ workspace, route }: { workspace: Loaded; route: Route }) {
  const { api, makeId, preferences, openTab } = useDeps();
  const notify = useNotify();
  const drawers = useDrawers();
  const shell = useRef<HTMLDivElement>(null);
  const layout = useDrawerLayout(shell);
  /** Whether the panels are drawers (see `logic/layout.ts`). */
  const drawerMode = layout === true;
  useKeyboardOffset();
  const { at, manuscript, section } = workspace;
  const volume = manuscript.volumes.find((v) => v.id === at.volume);
  const initial = workspace.recovered?.document ?? workspace.draft.document;

  const editorRef = useRef<Editor | null>(null);
  const reader = useMemo<EditorReader>(
    () => ({
      document: () => pmToLogos(editorRef.current!.getJSON(), makeId),
      caret: () => {
        const view = editorRef.current;
        return view ? caretAt(view.state.doc, view.state.selection.from) : null;
      },
    }),
    [makeId],
  );

  const session = useDraftSession(workspace, reader);
  const coach = useCoach(at.book, reader.document);
  const review = useEditorReview(at, session.drafts.current.id, session.actions.settled);
  const akasha = useAkasha(at.book);
  const [askName, nameDialog] = useNameDialog();

  const [placement, setPlacement] = useState<Placement>({});
  const [focused, setFocused] = useState<string | null>(null);
  const [popover, setPopover] = useState<string | null>(null);
  const [tab, setTab] = useState<Panel>(route.panel ?? "akasha");
  const [selectedIssue, setSelectedIssue] = useState<string | null>(null);
  const [menu, setMenu] = useState<MenuRequest | null>(null);
  const [comparing, setComparing] = useState(false);
  const [words, setWords] = useState(() => wordCount(initial));
  const [layers, setLayersState] = useState<Layers>(() => preferences.layers());
  const [ask, setAsk] = useState(() => ({
    ...preferences.reviewOptions(),
    include: [] as AskSettings["include"],
  }));

  /** Run a draft action; if it fails, say so rather than fail silently. */
  const attempt = (action: () => Promise<unknown> | unknown) =>
    void Promise.resolve()
      .then(action)
      .catch((error) =>
        notify({
          title: "That did not work",
          description: messageOf(error),
          tone: "danger",
        }),
      );

  const openTools = useCallback(
    (next: Panel) => {
      setTab(next);
      if (drawerMode) drawers.show("tools");
    },
    [drawers, drawerMode],
  );

  const lookUp = useCallback((): boolean => {
    const view = editorRef.current;
    if (!view) return false;
    const { from, to } = view.state.selection;
    const text = from === to ? null : lookupText(view.state.doc.textBetween(from, to, " "));
    if (!text) return false;
    akasha.setSubject({
      kind: "lookup",
      text,
      range: { from, to },
      linkable: linkable(view.state, { from, to }),
    });
    openTools("akasha");
    return true;
  }, [akasha, openTools]);

  const editor = useWriterEditor(initial, makeId, `Edit ${sectionName(section)}`, {
    onChange: () => {
      session.changed();
      setWords(wordCount(reader.document()));
      coach.schedule();
    },
    onActivate: (id) => {
      setFocused(id);
      setPopover(id);
    },
    onPlacement: setPlacement,
    onSave: session.actions.saveNow,
    onLookUp: lookUp,
  });
  useLayoutEffect(() => {
    editorRef.current = editor;
  }, [editor]);

  // -- notes: what is drawn, and what is open ------------------------------------

  const issues = useMemo(() => review.review?.issues ?? [], [review.review]);
  const issuesRef = useLatest(issues);
  const notes = useMemo(() => {
    const all = new Map<string, Note>();
    if (review.review)
      for (const issue of issues)
        all.set(editorAnnotationId(issue), editorNote(issue, review.review.id));
    for (const issue of coach.issues) all.set(coachNote(issue).id, coachNote(issue));
    return all;
  }, [issues, review.review, coach.issues]);

  const annotations = useMemo(
    () => [
      ...(layers.editor ? editorAnnotations(issues) : []),
      ...(layers.coach ? coachAnnotations(coach.issues) : []),
    ],
    [layers, issues, coach.issues],
  );
  useEffect(() => {
    editor.commands.setAnnotations(annotations);
  }, [editor, annotations]);
  useEffect(() => {
    editor.commands.setActiveAnnotation(focused);
  }, [editor, focused]);

  // A note whose words are gone, or that was set aside, has nothing to point at.
  const openNote =
    popover && placement[popover] != null ? (notes.get(popover) ?? null) : null;

  const reveal = useCallback(
    (note: Note) => {
      if (drawerMode) drawers.close(false);
      setFocused(note.id);
      window.requestAnimationFrame(() => {
        underline(note.id)?.scrollIntoView({ block: "center", behavior: "smooth" });
        setPopover(note.id);
      });
    },
    [drawers, drawerMode],
  );

  const actions = useNoteActions({
    editor,
    review,
    coach,
    issueNow: (id) => issuesRef.current.find((issue) => issue.id === id),
    openIssue: (id) => {
      setSelectedIssue(id);
      openTools("editor");
    },
    reveal,
    closeNote: () => setPopover(null),
    toProse: () => drawerMode && drawers.close(false),
  });

  const selectIssue = (id: string | null, show = false) => {
    setSelectedIssue(id);
    if (!id) return;
    const annotation = `editor:${id}`;
    setFocused(annotation);
    if (show)
      underline(annotation)?.scrollIntoView({ block: "center", behavior: "smooth" });
  };

  // -- Akasha ---------------------------------------------------------------------

  const link = (entity: Entity) => {
    if (akasha.subject.kind !== "lookup") return;
    const { range, text } = akasha.subject;
    const still =
      lookupText(editor.state.doc.textBetween(range.from, range.to, " ")) === text;
    if (!still || !editor.commands.linkMention(range, entity)) {
      notify({
        title: "Those words have changed",
        description: "Select them again to link them.",
        tone: "danger",
      });
      return;
    }
    const linked = mentionAt(editor.state, range.from);
    akasha.setSubject(linked ? { kind: "mention", mention: linked } : { kind: "idle" });
  };

  const unlink = () => {
    if (akasha.subject.kind !== "mention") return;
    const { mention } = akasha.subject;
    editor.commands.unlinkMention(mention.range.from);
    akasha.setSubject({ kind: "idle" });
    notify({
      title: `“${mention.text}” is no longer linked`,
      description: "The words are unchanged.",
    });
  };

  const openArticle = (ref: { database: string; collection: string; id: string }) =>
    openTab(api.articleUrl(ref));

  const contextMenu = (event: MouseEvent) => {
    const found: MenuAction[] = [];
    const pos = editor.view.posAtCoords({ left: event.clientX, top: event.clientY })?.pos;
    const mention = pos == null ? null : mentionAt(editor.state, pos);
    if (mention) {
      found.push({
        label: `Open “${mention.text}” in Akasha`,
        run: () => openArticle(mention),
      });
      found.push({
        label: "Unlink these words",
        run: () => editor.commands.unlinkMention(mention.range.from),
      });
    }
    const { from, to } = editor.state.selection;
    const text =
      from === to ? null : lookupText(editor.state.doc.textBetween(from, to, " "));
    if (text)
      found.push({ label: `Look up “${text}” in Akasha`, run: () => void lookUp() });
    if (!found.length) return; // the browser's own menu: paste, spelling
    event.preventDefault();
    setMenu({ x: event.clientX, y: event.clientY, actions: found });
  };

  const clickProse = (event: MouseEvent) => {
    const target = event.target instanceof Element ? event.target : null;
    // A note underlined on a linked name opens the note, not the link.
    if (target?.closest("[data-annotation]")) return;
    const element = target?.closest(".entity-mention");
    if (!element) return;
    const mention = mentionAt(editor.state, editor.view.posAtDOM(element, 0));
    if (!mention) return;
    akasha.setSubject({ kind: "mention", mention });
    openTools("akasha");
  };

  // -- landing --------------------------------------------------------------------

  const landed = useRef(false);
  useEffect(() => {
    // Once, on arrival -- as soon as the layout is known, so a phone asked for
    // a panel gets it as a drawer.
    if (layout === null || landed.current) return;
    landed.current = true;
    if (route.panel && layout) drawers.show("tools");
    const doc = editor.state.doc;
    const caret = workspace.recovered?.caret;
    const resumed = caret ? caretPos(doc, caret) : null;
    const block = route.block ? findBlock(doc, route.block) : null;
    const pos = resumed ?? (block ? block.pos + block.node.nodeSize - 1 : null);
    if (pos != null) {
      editor
        .chain()
        .setTextSelection(pos)
        .focus(undefined, { scrollIntoView: false })
        .run();
      window.requestAnimationFrame(() => {
        const { node } = editor.view.domAtPos(pos);
        (node instanceof Element ? node : node.parentElement)?.scrollIntoView({
          block: "center",
        });
      });
    } else {
      editor.commands.focus("start", { scrollIntoView: false });
    }
  }, [layout, drawers, editor, route.block, route.panel, workspace.recovered]);

  // -- the page ---------------------------------------------------------------------

  const openCount = issues.filter((issue) => issue.status === "open").length;
  const setLayers = (next: Layers) => {
    preferences.setLayers(next);
    setLayersState(next);
  };

  return (
    <div
      ref={shell}
      className={`lw-shell${drawerMode ? " is-drawers" : ""}${drawers.open ? ` has-${drawers.open}` : ""}`}
    >
      <TopBar
        where={`${volume?.title ?? ""} / ${sectionName(section)}`}
        backHref={api.contentsUrl(at.book)}
        drafts={session.drafts}
        words={words}
        status={session.status}
        openDrawer={drawers.open}
        toolsCount={openCount}
        actions={{
          back: () => attempt(() => session.actions.leave(api.contentsUrl(at.book))),
          switchDraft: (id) => attempt(() => session.actions.switchDraft(id)),
          newDraft: () =>
            attempt(async () => {
              const name = await askName(
                "Name the new draft",
                `Draft ${session.drafts.rows.length + 1}`,
              );
              if (name) await session.actions.newDraft(name);
            }),
          rename: () =>
            attempt(async () => {
              const name = await askName("Rename draft", session.drafts.current.name);
              if (name && name !== session.drafts.current.name)
                session.actions.rename(name);
            }),
          makePrimary: () => attempt(session.actions.makePrimary),
          compare: () =>
            attempt(async () => {
              if (await session.actions.settled()) setComparing(true);
            }),
          preserve: () => attempt(session.actions.preserveConflict),
          toggleOutline: () => drawers.toggle("outline"),
          toggleTools: () => drawers.toggle("tools"),
          done: () => attempt(session.actions.done),
        }}
      />
      <div className="lw-columns">
        <OutlinePanel
          manuscript={manuscript}
          at={at}
          hrefFor={(v, s) => api.writerUrl({ book: at.book, volume: v, section: s })}
          onOpen={(url) => attempt(() => session.actions.leave(url))}
          onNewChapter={(v) =>
            attempt(async () => {
              const title = await askName(
                "Name the new chapter",
                "Untitled chapter",
                "Chapter title",
              );
              if (title) await session.actions.createChapter(v, title);
            })
          }
          onClose={() => drawers.close()}
        />
        <main className="lw-page">
          <p className="lw-eyebrow">
            Volume {volume?.number} · {sectionLabel(section)}
          </p>
          <input
            className="lw-title"
            value={session.title}
            maxLength={300}
            placeholder={sectionLabel(section)}
            aria-label="Section title"
            onChange={(event) => session.setTitle(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                editor.commands.focus("start");
              }
            }}
          />
          <FormatBar editor={editor} />
          <div className="lw-prose-frame" onContextMenu={contextMenu} onClick={clickProse}>
            <EditorContent editor={editor} />
          </div>
        </main>
        <ToolsPanel
          tab={tab}
          onTab={setTab}
          onClose={() => drawers.close()}
          counts={{ coach: coach.issues.length, editor: openCount }}
          akasha={
            <AkashaTab
              subject={akasha.subject}
              results={akasha.results}
              onLink={link}
              onOpen={openArticle}
              onUnlink={unlink}
            />
          }
          coach={
            <CoachTab
              coach={coach}
              placement={placement}
              actions={actions}
              marked={layers.coach}
              onMarked={(coachOn) => setLayers({ ...layers, coach: coachOn })}
            />
          }
          editor={
            <EditorTab
              review={review}
              at={at}
              draftId={session.drafts.current.id}
              settled={session.actions.settled}
              settings={{ ...ask, dialect: coach.dialect }}
              onSettings={({ checks, verify, include, dialect }) => {
                preferences.setReviewOptions({ checks, verify });
                setAsk({ checks, verify, include });
                if (dialect !== coach.dialect) coach.setDialect(dialect);
              }}
              placement={placement}
              blockOrder={editor.state.doc.content.content.map(
                (node) => node.attrs.id as string,
              )}
              selected={selectedIssue}
              onSelect={selectIssue}
              actions={actions}
              marked={layers.editor}
              onMarked={(editorOn) => setLayers({ ...layers, editor: editorOn })}
            />
          }
        />
      </div>
      <button
        type="button"
        className="lw-backdrop"
        aria-label="Close open writing panel"
        onClick={() => drawers.close()}
      />
      <ContextMenu request={menu} onClose={() => setMenu(null)} />
      <NotePopover
        note={openNote}
        references={review.review?.references}
        actions={actions}
        onClose={() => {
          setPopover(null);
          setFocused(null);
        }}
      />
      {nameDialog}
      {comparing ? (
        <CompareDialog
          at={at}
          rows={session.drafts.rows}
          open
          onOpenChange={(open) => !open && setComparing(false)}
        />
      ) : null}
    </div>
  );
}
