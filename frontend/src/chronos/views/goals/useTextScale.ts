// The reader's text size relative to the default. The diagram is laid out in
// pixels and its labels in rem, so without this a larger text setting would
// grow the words inside boxes that stayed the same size. The font toggle sets
// the root font size inline, which is the one thing worth watching for.

import { useEffect, useState } from "react";

export function readTextScale(root: HTMLElement = document.documentElement): number {
  return (parseFloat(getComputedStyle(root).fontSize) || 16) / 16;
}

export function useTextScale(): number {
  const [scale, setScale] = useState(readTextScale);
  useEffect(() => {
    if (typeof MutationObserver !== "function") return;
    const watch = new MutationObserver(() => setScale(readTextScale()));
    watch.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["style"],
    });
    return () => watch.disconnect();
  }, []);
  return scale;
}
