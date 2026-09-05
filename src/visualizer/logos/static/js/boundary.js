// A geometry-free accumulator for deliberate scrolling beyond a section edge.
// Browsers do not expose useful swipe "pressure", so intent is measured as
// same-direction distance within a short window.

export function boundaryGesture({ threshold = 140, windowMs = 700 } = {}) {
  let total = 0;
  let direction = null;
  let lastAt = 0;
  let locked = false;

  const reset = () => {
    total = 0;
    direction = null;
    lastAt = 0;
    locked = false;
    return { direction: null, progress: 0, trigger: null };
  };

  const push = ({ delta, atStart, atEnd, now }) => {
    const wanted = delta > 0 && atEnd ? "next"
      : delta < 0 && atStart ? "previous" : null;
    if (!wanted) return reset();
    if (locked) return { direction: wanted, progress: 1, trigger: null };
    if (wanted !== direction || now - lastAt > windowMs) total = 0;
    direction = wanted;
    lastAt = now;
    total += Math.abs(delta);
    const progress = Math.min(1, total / threshold);
    if (total < threshold) return { direction, progress, trigger: null };
    locked = true;
    return { direction, progress: 1, trigger: direction };
  };

  return { push, reset };
}
