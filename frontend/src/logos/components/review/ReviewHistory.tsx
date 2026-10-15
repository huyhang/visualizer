// The section's kept reviews, newest first, to look back at one.

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
  onChoose,
}: {
  reviews: ReviewSummary[];
  viewing: string | null;
  onChoose: (id: string) => void;
}) {
  if (reviews.length < 2) return null;
  return (
    <details className="lw-history">
      <summary>Earlier reviews ({reviews.length - 1})</summary>
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
              <small>{counts(review)}</small>
            </button>
          </li>
        ))}
      </ol>
    </details>
  );
}
