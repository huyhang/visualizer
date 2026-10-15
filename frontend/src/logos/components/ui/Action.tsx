// A button that is an icon and a word, and just the icon when the bar runs out
// of room. The word stays its accessible name and its tooltip either way --
// the convention the reader's compact actions follow.

import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Icon, type IconName } from "../../../components/ui/Icon";

interface ActionProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  icon: IconName;
  label: string;
  tone?: "ghost" | "primary" | "accent" | "danger";
  /** Show the word at every width, not only when there is room. */
  keepLabel?: boolean;
  children?: ReactNode;
}

export function Action({
  icon,
  label,
  tone = "ghost",
  keepLabel = false,
  className = "",
  type = "button",
  children,
  ...rest
}: ActionProps) {
  return (
    <button
      type={type}
      className={`lw-action lw-action-${tone}${keepLabel ? " keeps-label" : ""} ${className}`.trim()}
      aria-label={label}
      title={label}
      {...rest}
    >
      <Icon name={icon} size={16} />
      <span className="lw-action-label">{label}</span>
      {children}
    </button>
  );
}
