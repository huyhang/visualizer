// Small words and numbers for the writer.

export function plural(n: number, one: string, many = `${one}s`): string {
  return `${n} ${n === 1 ? one : many}`;
}

const UNITS: [number, string][] = [
  [60, "second"],
  [60, "minute"],
  [24, "hour"],
  [7, "day"],
  [4.35, "week"],
  [12, "month"],
  [Number.POSITIVE_INFINITY, "year"],
];

export function timeAgo(iso: string | null | undefined, now: Date = new Date()): string {
  if (!iso) return "";
  const then = new Date(iso);
  if (Number.isNaN(then.getTime())) return "";
  let amount = Math.max(0, (now.getTime() - then.getTime()) / 1000);
  if (amount < 45) return "just now";
  for (const [size, unit] of UNITS) {
    if (amount < size) {
      const n = Math.round(amount);
      return `${plural(n, unit)} ago`;
    }
    amount /= size;
  }
  return "";
}

/** "research-inbox/song-tea" -> "song-tea". */
export function slugOf(ref: string): string {
  return ref.slice(ref.indexOf("/") + 1);
}

/** The host of a URL, without "www.", for a source's byline. */
export function siteOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}
