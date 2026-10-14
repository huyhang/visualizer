import { Popover } from "radix-ui";
import type { Availability } from "../../api/types";
import { boxLabel, boxTone, verifierLine } from "../../logic/availability";
import { StatusDot } from "../ui/StatusDot";

/** The GPU box's state as a pill; its details on click. */
export function BoxStatus({ availability }: { availability: Availability | undefined }) {
  if (!availability) {
    return (
      <span className="st-box-pill is-loading">
        <StatusDot tone="muted" /> Checking the GPU box…
      </span>
    );
  }
  const tone = boxTone(availability.state);
  return (
    <Popover.Root>
      <Popover.Trigger className={`st-box-pill is-${tone}`}>
        <StatusDot tone={tone} pulse={availability.state === "cold"} />
        Researcher · {boxLabel(availability.state)}
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content className="st-popover st-box-details" sideOffset={8} align="start">
          <p className="st-box-message">{availability.message}</p>
          {availability.model ? (
            <dl>
              <dt>Model</dt>
              <dd>{availability.model}</dd>
              <dt>Checks</dt>
              <dd>{verifierLine(availability)}</dd>
              <dt>Privacy</dt>
              <dd>
                {availability.private ? "Runs on your own hardware." : "Runs elsewhere."}
              </dd>
            </dl>
          ) : null}
          <Popover.Arrow className="st-popover-arrow" />
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
