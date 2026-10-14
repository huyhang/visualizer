import { useLayoutEffect, useRef, type TextareaHTMLAttributes } from "react";

/** A textarea that grows with what is typed into it, up to `maxRows`. */
export function AutoTextarea({
  maxRows = 12,
  value,
  className = "",
  ...rest
}: TextareaHTMLAttributes<HTMLTextAreaElement> & { maxRows?: number; value: string }) {
  const ref = useRef<HTMLTextAreaElement>(null);
  useLayoutEffect(() => {
    const area = ref.current;
    if (!area) return;
    area.style.height = "auto";
    const line = parseFloat(getComputedStyle(area).lineHeight) || 20;
    area.style.height = `${Math.min(area.scrollHeight, line * maxRows + 16)}px`;
  }, [value, maxRows]);
  return (
    <textarea
      ref={ref}
      value={value}
      className={`st-textarea ${className}`.trim()}
      {...rest}
    />
  );
}
