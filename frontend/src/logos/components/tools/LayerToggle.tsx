import { Switch } from "radix-ui";
import { useId } from "react";

/** Whether one source's notes are underlined in the manuscript. */
export function LayerToggle({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  const id = useId();
  return (
    <span className="lw-layer">
      <Switch.Root
        id={id}
        className="lw-switch"
        checked={checked}
        onCheckedChange={onChange}
      >
        <Switch.Thumb className="lw-switch-thumb" />
      </Switch.Root>
      <label htmlFor={id}>{label}</label>
    </span>
  );
}
