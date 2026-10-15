// A screen's frame: a heading block, then the content, in a pane that scrolls
// on its own while the sidebar and inspector stay put.

import type { ReactNode } from "react";

export function Page({
  children,
  wide = false,
  label,
}: {
  children: ReactNode;
  /** Let the content use the whole pane: the map and the scene timeline do. */
  wide?: boolean;
  label: string;
}) {
  return (
    <section className={`cw-page${wide ? " is-wide" : ""}`} aria-label={label}>
      <div className="cw-page-inner">{children}</div>
    </section>
  );
}

export function PageHeader({
  eyebrow,
  title,
  subtitle,
  actions,
  children,
}: {
  eyebrow?: ReactNode;
  title: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <header className="cw-page-head">
      <div className="cw-page-titles">
        {eyebrow ? <div className="cw-eyebrow">{eyebrow}</div> : null}
        <h1 className="cw-page-title">{title}</h1>
        {subtitle ? <p className="cw-page-sub">{subtitle}</p> : null}
      </div>
      {actions ? <div className="cw-page-actions">{actions}</div> : null}
      {children ? <div className="cw-page-tools">{children}</div> : null}
    </header>
  );
}
