// Formatting: undo and redo, the four marks Logos stores, the two lists, and
// paragraph or heading. Pinned under the bar on a wide screen; docked at the
// foot of a narrow one, above the on-screen keyboard.

import type { Editor } from "@tiptap/core";
import { useEditorState } from "@tiptap/react";
import { Icon, type IconName } from "../../../components/ui/Icon";
import { currentBlockStyle, type BlockStyle } from "../../editor/blockStyle";

interface Tool {
  label: string;
  shortcut: string;
  active?: boolean;
  disabled?: boolean;
  run: () => void;
  glyph: IconName | string;
}

const STYLES: { value: string; long: string; short: string }[] = [
  { value: "p", long: "Paragraph", short: "P" },
  { value: "1", long: "Heading 1", short: "H1" },
  { value: "2", long: "Heading 2", short: "H2" },
  { value: "3", long: "Heading 3", short: "H3" },
];

function ToolButton({ tool }: { tool: Tool }) {
  const icon = tool.glyph.length > 2;
  return (
    <button
      type="button"
      className={`lw-tool${tool.active ? " is-active" : ""}`}
      aria-label={tool.label}
      aria-pressed={tool.active ?? undefined}
      title={`${tool.label} (${tool.shortcut})`}
      disabled={tool.disabled}
      // Keep the selection in the prose: a button that takes focus takes it away.
      onMouseDown={(event) => event.preventDefault()}
      onClick={tool.run}
    >
      {icon ? (
        <Icon name={tool.glyph as IconName} size={17} />
      ) : (
        <span className={`lw-tool-glyph lw-tool-${tool.label.toLowerCase()}`}>
          {tool.glyph}
        </span>
      )}
    </button>
  );
}

export function FormatBar({ editor }: { editor: Editor }) {
  const state = useEditorState({
    editor,
    selector: ({ editor: e }) => ({
      strong: e.isActive("strong"),
      em: e.isActive("em"),
      strike: e.isActive("strike"),
      bullets: e.isActive("bullet_list"),
      numbered: e.isActive("ordered_list"),
      style: currentBlockStyle(e.state),
      canUndo: e.can().undo(),
      canRedo: e.can().redo(),
    }),
  });
  const chain = () => editor.chain().focus();
  const tools: Tool[] = [
    {
      label: "Undo",
      shortcut: "⌘Z",
      glyph: "undo",
      disabled: !state.canUndo,
      run: () => chain().undo().run(),
    },
    {
      label: "Redo",
      shortcut: "⇧⌘Z",
      glyph: "redo",
      disabled: !state.canRedo,
      run: () => chain().redo().run(),
    },
    {
      label: "Bold",
      shortcut: "⌘B",
      glyph: "B",
      active: state.strong,
      run: () => chain().toggleMark("strong").run(),
    },
    {
      label: "Italic",
      shortcut: "⌘I",
      glyph: "I",
      active: state.em,
      run: () => chain().toggleMark("em").run(),
    },
    {
      label: "Strikethrough",
      shortcut: "⇧⌘S",
      glyph: "S",
      active: state.strike,
      run: () => chain().toggleMark("strike").run(),
    },
    {
      label: "Bullets",
      shortcut: "⇧⌘8",
      glyph: "list",
      active: state.bullets,
      run: () => chain().toggleLogosList("bullet_list").run(),
    },
    {
      label: "Numbered",
      shortcut: "⇧⌘7",
      glyph: "listOrdered",
      active: state.numbered,
      run: () => chain().toggleLogosList("ordered_list").run(),
    },
  ];
  const setStyle = (value: string) =>
    chain()
      .setBlockStyle((value === "p" ? "p" : Number(value)) as BlockStyle)
      .run();
  const style = state.style === null ? "" : String(state.style);
  return (
    <div className="lw-format" role="toolbar" aria-label="Formatting">
      <div className="lw-format-group">
        {tools.slice(0, 2).map((tool) => (
          <ToolButton key={tool.label} tool={tool} />
        ))}
      </div>
      <span className="lw-format-rule" aria-hidden="true" />
      <div className="lw-format-group">
        {tools.slice(2, 5).map((tool) => (
          <ToolButton key={tool.label} tool={tool} />
        ))}
      </div>
      <span className="lw-format-rule" aria-hidden="true" />
      <div className="lw-format-group">
        {tools.slice(5).map((tool) => (
          <ToolButton key={tool.label} tool={tool} />
        ))}
      </div>
      <label className="lw-style">
        <span className="st-sr-only">Block style</span>
        <select
          aria-label="Block style"
          value={style}
          disabled={state.style === null}
          onChange={(event) => setStyle(event.target.value)}
        >
          {state.style === null ? <option value="">List</option> : null}
          {STYLES.map((option) => (
            <option key={option.value} value={option.value}>
              {option.long}
            </option>
          ))}
        </select>
        <span className="lw-style-short" aria-hidden="true">
          {STYLES.find((option) => option.value === style)?.short ?? "•"}
        </span>
      </label>
    </div>
  );
}
