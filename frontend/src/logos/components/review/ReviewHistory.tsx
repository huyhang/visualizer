// The section's kept reviews, newest first, to look back at one -- each with
// the draft it read, when the section has more than one.

import type { ReviewSummary } from "../../api/types";

const when = (iso: string) =>
  new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });

function counts(review: ReviewSummary): string {
  if (review.state === "running" || review.state === "queued") return "In progress";
  if (review.state === "failed") return "Failed";
  if (review.state === "cancelled") return "Cancelled";
  const total = review.issue_count ?? 0;
  if (!total) return "No issues";
  return `${review.open ?? 0} open of ${total}`;
}

export function ReviewHistory({
  reviews,
  viewing,
  draftNames,
  onChoose,
}: {
  reviews: ReviewSummary[];
  viewing: string | null;
  draftNames: Record<string, string>;
  onChoose: (id: string) => void;
}) {
  const others = reviews.filter((review) => review.id !== viewing).length;
  if (!others) return null;
  const named = Object.keys(draftNames).length > 1;
  return (
    <details className="lw-history">
      <summary>Other reviews ({others})</summary>
      <ol>
        {reviews.map((review) => (
          <li key={review.id}>
            <button
              type="button"
              className={review.id === viewing ? "is-current" : undefined}
              aria-current={review.id === viewing || undefined}
              onClick={() => onChoose(review.id)}
            >
              <span>{when(review.created_at)}</span>
              <small>
                {counts(review)}
                {named ? ` · ${draftNames[review.draft] ?? "a deleted draft"}` : ""}
              </small>
            </button>
          </li>
        ))}
      </ol>
    </details>
  );
}
