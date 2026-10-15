import { fixDiff } from "../../logic/fixDiff";

/** Spaces made visible, for a fix that only changes spacing. */
const shown = (text: string) => (text && !text.trim() ? text.replace(/ /g, "␣") : text);

/** The quoted words as the fix would leave them: what goes struck through, what arrives. */
export function FixPreview({ quote, replacement }: { quote: string; replacement: string }) {
  const diff = fixDiff(quote, replacement);
  const spacing = !quote.trim() && !replacement.trim();
  return (
    <p className="lw-fix" aria-label={`Replace “${quote}” with “${replacement}”`}>
      {spacing ? (
        <>
          <del>{shown(quote)}</del>
          <ins>{shown(replacement)}</ins>
        </>
      ) : (
        <>
          {diff.before}
          {diff.removed ? <del>{shown(diff.removed)}</del> : null}
          {diff.added ? <ins>{shown(diff.added)}</ins> : null}
          {diff.after}
        </>
      )}
    </p>
  );
}
