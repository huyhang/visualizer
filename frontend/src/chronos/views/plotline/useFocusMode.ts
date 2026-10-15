// Focus mode's switch, remembered under the classic page's key so both pages
// agree. The screen applies it as one class: nothing is re-read or re-judged.

import { useCallback, useState } from "react";
import { useDeps } from "../../deps";
import { FOCUS_KEY, isHidden } from "../../logic/plotline/focus";

export function useFocusMode(): [boolean, () => void] {
  const { store } = useDeps();
  const [hidden, setHidden] = useState(() => isHidden(store.get(FOCUS_KEY)));
  const toggle = useCallback(() => {
    setHidden((was) => {
      store.set(FOCUS_KEY, was ? "0" : "1");
      return !was;
    });
  }, [store]);
  return [hidden, toggle];
}
