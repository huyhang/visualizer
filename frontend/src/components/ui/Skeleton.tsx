/** Grey bars where text is about to be, so the page does not jump when it lands. */
export function Skeleton({ lines = 3 }: { lines?: number }) {
  return (
    <div className="st-skeleton" aria-hidden="true">
      {Array.from({ length: lines }, (_, n) => (
        <span key={n} style={{ width: `${92 - ((n * 17) % 40)}%` }} />
      ))}
    </div>
  );
}
