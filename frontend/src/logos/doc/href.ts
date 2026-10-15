/** `value` if Logos would store it as a link -- http, https or site-relative -- else null. */
export function safeHref(value: string | null | undefined): string | null {
  const href = (value ?? "").trim();
  if (!href || href.startsWith("//")) return null;
  if (href.startsWith("/")) return href;
  try {
    return ["http:", "https:"].includes(new URL(href).protocol) ? href : null;
  } catch {
    return null;
  }
}
