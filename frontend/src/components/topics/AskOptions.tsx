import { Popover } from "radix-ui";
import { parseLanguages, type AskOptions } from "../../logic/ask";
import { IconButton } from "../ui/Button";

/** The ask box's settings, tucked behind a cog: sensible defaults, rarely changed. */
export function AskOptionsMenu({
  options,
  onChange,
}: {
  options: AskOptions;
  onChange: (options: AskOptions) => void;
}) {
  const languages = parseLanguages(options.languages);
  const set = <K extends keyof AskOptions>(key: K, value: AskOptions[K]) =>
    onChange({ ...options, [key]: value });

  return (
    <Popover.Root>
      <Popover.Trigger asChild>
        <IconButton icon="settings" label="Research settings" />
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content className="st-popover st-ask-options" sideOffset={8} align="end">
          <label className="st-check">
            <input
              type="checkbox"
              checked={options.reviewPlan}
              onChange={(e) => set("reviewPlan", e.target.checked)}
            />
            <span>
              <strong>Let me check the search plan first</strong>
              <small>See and edit the searches before any page is read.</small>
            </span>
          </label>
          <label className="st-check">
            <input
              type="checkbox"
              checked={options.includeImages}
              onChange={(e) => set("includeImages", e.target.checked)}
            />
            <span>
              <strong>Look for images</strong>
              <small>Openly licensed pictures you can add to a note.</small>
            </span>
          </label>
          <label className="st-field">
            <span>
              Sources to read <output>{options.maxSources}</output>
            </span>
            <input
              type="range"
              min={1}
              max={15}
              value={options.maxSources}
              onChange={(e) => set("maxSources", Number(e.target.value))}
            />
          </label>
          <label className="st-field">
            <span>Languages to search</span>
            <input
              className="st-input"
              value={options.languages}
              onChange={(e) => set("languages", e.target.value)}
              aria-invalid={typeof languages === "string"}
              placeholder="en, zh"
            />
            {typeof languages === "string" ? (
              <small className="st-error-text">{languages}</small>
            ) : null}
          </label>
          <label className="st-field">
            <span>Second check</span>
            <select
              className="st-input"
              value={options.verify}
              onChange={(e) => set("verify", e.target.value as AskOptions["verify"])}
            >
              <option value="auto">When the checker is up</option>
              <option value="required">Always — wait for the checker</option>
              <option value="off">Never</option>
            </select>
          </label>
          <Popover.Arrow className="st-popover-arrow" />
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
