import type { VerificationReport } from "../../api/types";
import { Badge } from "../ui/Badge";
import { Icon } from "../ui/Icon";

/** Whether a second machine checked this draft's facts -- the inbox must say. */
export function VerificationBadge({ report }: { report: VerificationReport | null }) {
  if (!report) return null;
  if (report.status === "checked") {
    const removed = report.removed ? `, ${report.removed} removed` : "";
    return (
      <Badge
        tone="ok"
        title={`Checked by ${report.model ?? "the verifier"}: ${report.checked} facts${removed}.`}
      >
        <Icon name="shield" size={12} /> Second-checked
      </Badge>
    );
  }
  if (report.status === "skipped") {
    return (
      <Badge tone="warn" title={report.reason ?? "The second checker was unavailable."}>
        First pass only
      </Badge>
    );
  }
  return (
    <Badge title="The second check was switched off for this question.">
      No second check
    </Badge>
  );
}
