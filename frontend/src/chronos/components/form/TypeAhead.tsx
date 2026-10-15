// A type-ahead: search something as you type, choose with the arrows and
// Enter. It does not know what it is choosing -- the caller supplies the search
// and how a result reads -- so the scene picker, the article picker and the
// "continues into" picker are all this one component.

import { useEffect, useId, useState, type KeyboardEvent, type ReactNode } from "react";
import { useDebounced } from "../common/Fields";
import { Icon } from "../../../components/ui/Icon";

export interface Option<T> {
  key: string;
  value: T;
  label: string;
  hint?: string;
}

export function TypeAhead<T>({
  search,
  onPick,
  placeholder,
  label,
  renderOption,
  autoFocus,
  emptyText = "Nothing matches.",
}: {
  /** The options for what was typed; called again (debounced) as typing continues. */
  search: (query: string) => Promise<Option<T>[]> | Option<T>[];
  onPick: (value: T, option: Option<T>) => void;
  placeholder: string;
  label: string;
  renderOption?: (option: Option<T>) => ReactNode;
  autoFocus?: boolean;
  /** What to say when the search finds nothing: where to go instead, ideally. */
  emptyText?: string;
}) {
  const id = useId();
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [options, setOptions] = useState<Option<T>[]>([]);
  const [active, setActive] = useState(0);
  const settled = useDebounced(query, 150);

  useEffect(() => {
    if (!open) return;
    let live = true;
    Promise.resolve(search(settled))
      .then((found) => {
        if (!live) return;
        setOptions(found);
        setActive(0);
      })
      .catch(() => live && setOptions([]));
    return () => {
      live = false;
    };
  }, [settled, open, search]);

  const pick = (option: Option<T> | undefined) => {
    if (!option) return;
    onPick(option.value, option);
    setQuery("");
    setOpen(false);
  };
  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      setOpen(true);
      const step = e.key === "ArrowDown" ? 1 : -1;
      setActive((n) => (options.length ? (n + step + options.length) % options.length : 0));
    } else if (e.key === "Enter") {
      if (open && options.length) {
        e.preventDefault();
        pick(options[active]);
      }
    } else if (e.key === "Escape" && open) {
      // Handled: the dialog around it (see Modal) and the inspector leave it be.
      e.preventDefault();
      setOpen(false);
    }
  };

  return (
    <div className="cw-typeahead">
      <div className="cw-typeahead-field">
        <Icon name="search" size={14} />
        <input
          className="cw-typeahead-input"
          role="combobox"
          aria-label={label}
          aria-expanded={open}
          aria-controls={`${id}-list`}
          aria-activedescendant={open && options[active] ? `${id}-${active}` : undefined}
          autoFocus={autoFocus}
          placeholder={placeholder}
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 120)}
          onKeyDown={onKeyDown}
        />
      </div>
      {open ? (
        <ul className="cw-typeahead-list st-popover" id={`${id}-list`} role="listbox">
          {options.map((o, n) => (
            <li
              key={o.key}
              id={`${id}-${n}`}
              role="option"
              aria-selected={n === active}
              className={`cw-typeahead-option${n === active ? " is-active" : ""}`}
              onMouseDown={(e) => e.preventDefault()}
              onMouseMove={() => setActive(n)}
              onClick={() => pick(o)}
            >
              {renderOption ? (
                renderOption(o)
              ) : (
                <>
                  <span className="cw-typeahead-label">{o.label}</span>
                  {o.hint ? <span className="cw-typeahead-hint">{o.hint}</span> : null}
                </>
              )}
            </li>
          ))}
          {options.length === 0 ? (
            <li className="cw-typeahead-empty">{emptyText}</li>
          ) : null}
        </ul>
      ) : null}
    </div>
  );
}
