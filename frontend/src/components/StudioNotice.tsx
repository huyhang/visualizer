import type { Availability } from "../api/types";
import { isNoAccess } from "../api/errors";
import { EmptyState } from "./ui/EmptyState";
import type { IconName } from "./ui/Icon";

export type Blocked = "off" | "no-access";

/**
 * Why none of the studio's panes could work, if so: research switched off on
 * this stack, or a world whose research this writer cannot read -- or one
 * that does not exist, which the server answers the same way rather than say
 * which.
 */
export function blockedBy(
  availability: Availability | undefined,
  jobsError: unknown,
): Blocked | null {
  if (availability?.state === "off") return "off";
  if (isNoAccess(jobsError)) return "no-access";
  return null;
}

const NOTICES: Record<Blocked, { icon: IconName; title: string; text: string }> = {
  off: {
    icon: "settings",
    title: "Research is off",
    text: "This Akasha has no GPU box set up, so there is no researcher to ask. Everything else works as usual.",
  },
  "no-access": {
    icon: "shield",
    title: "No research to show here",
    text: "Either there is no such world, or its research isn't shared with you. Ask the world's owner to share it.",
  },
};

/** One calm screen in place of three panes of errors. */
export function StudioNotice({ blocked }: { blocked: Blocked }) {
  const notice = NOTICES[blocked];
  return (
    <div className="st-studio is-blocked">
      <EmptyState icon={notice.icon} title={notice.title}>
        {notice.text}
      </EmptyState>
    </div>
  );
}
