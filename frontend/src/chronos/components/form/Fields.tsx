// Labelled form controls in the stack's field style. Each takes a value and
// says when it changes; none keeps state of its own.

import { useId, type ReactNode } from "react";

export function Field({
  label,
  hint,
  error,
  children,
  htmlFor,
}: {
  label: string;
  hint?: ReactNode;
  error?: string | null;
  children: ReactNode;
  htmlFor?: string;
}) {
  return (
    <div className="cw-field">
      <label className="cw-field-label" htmlFor={htmlFor}>
        {label}
      </label>
      {children}
      {error ? (
        <span className="cw-field-error" role="alert">
          {error}
        </span>
      ) : hint ? (
        <span className="cw-field-hint">{hint}</span>
      ) : null}
    </div>
  );
}

export function TextField({
  label,
  value,
  onChange,
  hint,
  error,
  placeholder,
  autoFocus,
  disabled,
  mono = false,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  hint?: ReactNode;
  error?: string | null;
  placeholder?: string;
  autoFocus?: boolean;
  disabled?: boolean;
  /** For ids: drawn in a fixed-width face so a stray character shows. */
  mono?: boolean;
}) {
  const id = useId();
  return (
    <Field label={label} hint={hint} error={error} htmlFor={id}>
      <input
        id={id}
        className={`st-input${mono ? " cw-mono" : ""}`}
        value={value}
        placeholder={placeholder}
        autoFocus={autoFocus}
        disabled={disabled}
        aria-invalid={error ? true : undefined}
        onChange={(e) => onChange(e.target.value)}
      />
    </Field>
  );
}

export function TextAreaField({
  label,
  value,
  onChange,
  hint,
  rows = 4,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  hint?: ReactNode;
  rows?: number;
  placeholder?: string;
}) {
  const id = useId();
  return (
    <Field label={label} hint={hint} htmlFor={id}>
      <textarea
        id={id}
        className="st-textarea cw-textarea"
        rows={rows}
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
      />
    </Field>
  );
}

export function SelectField({
  label,
  value,
  onChange,
  options,
  hint,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: { value: string; label: string }[];
  hint?: ReactNode;
}) {
  const id = useId();
  return (
    <Field label={label} hint={hint} htmlFor={id}>
      <select
        id={id}
        className="st-input"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </Field>
  );
}
