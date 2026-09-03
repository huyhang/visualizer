// Geometry-only section progress. Keeping this out of the DOM wiring makes the
// short-section and boundary rules explicit and independently testable.

const clamp = (value) => Math.min(1, Math.max(0, value));

export function sectionProgress({ top, height, scrollY, viewportHeight }) {
  if (![top, height, scrollY, viewportHeight].every(Number.isFinite)) return 0;
  if (height <= viewportHeight) return 1;
  return clamp((scrollY - top) / (height - viewportHeight));
}

export function scrollForProgress({ top, height, viewportHeight }, progress) {
  if (![top, height, viewportHeight].every(Number.isFinite)) return 0;
  const distance = Math.max(0, height - viewportHeight);
  return top + distance * clamp(Number.isFinite(progress) ? progress : 0);
}
