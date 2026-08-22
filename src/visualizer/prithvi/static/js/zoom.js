// Zoom arithmetic. Pure: numbers in, numbers out, no DOM.
//
// The one rule this module exists to enforce: the drawing's on-screen size is
// a function of (viewport, viewBox, zoom) and of nothing else. It is never
// derived from the size the drawing happens to have *right now*.
//
// That sounds pedantic until you write it the other way. `box = measured * zoom`
// reads fine and is wrong, because the thing you measured is the thing the last
// render sized: the height becomes a running product of every zoom factor ever
// applied, so 100% -> 125% -> 100% does not come back, and zooming *out* grows
// it (1.25 > 1). Keeping `fitBox` and `boxForZoom` separate and both pure makes
// that mistake unrepresentable -- and `test_geometry_js` walks a full zoom cycle
// to prove the round trip closes.

export const MIN_ZOOM = 0.5;
export const MAX_ZOOM = 4;
export const ZOOM_STEP = 0.25;

export function clampZoom(value) {
  if (!Number.isFinite(value)) return 1;
  return Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, value));
}

// The drawing at 100%: the largest box with the *map's* aspect ratio that fits
// the viewport. Sharing the viewBox's proportions is what leaves
// `preserveAspectRatio="xMidYMid meet"` nothing to letterbox, so the element
// and the picture are the same rectangle and there is no dead space to scale up.
export function fitBox(viewport, viewBox) {
  const [, , width, height] = viewBox || [];
  if (!(width > 0) || !(height > 0)) return { width: 0, height: 0 };
  if (!(viewport.width > 0) || !(viewport.height > 0)) return { width: 0, height: 0 };
  const scale = Math.min(viewport.width / width, viewport.height / height);
  return { width: width * scale, height: height * scale };
}

export function boxForZoom(fit, zoom) {
  return {
    width: Math.max(1, fit.width * zoom),
    height: Math.max(1, fit.height * zoom),
  };
}

// A wheel notch, as a multiplier rather than a step: trackpads send many small
// deltas and a mouse sends few large ones, and exponentiating the delta makes
// both feel the same.
export function zoomFromWheel(zoom, deltaY) {
  return clampZoom(zoom * Math.exp(-deltaY * 0.002));
}

// Where to scroll so the point that was under `offset` before the resize is
// under `offset` after it. `ratio` is that point as a fraction of the old
// scrollable size.
export function anchoredScroll(ratio, scrollSize, offset) {
  return Math.max(0, ratio * scrollSize - offset);
}

export function scrollRatio(scrollPos, offset, scrollSize) {
  return scrollSize > 0 ? (scrollPos + offset) / scrollSize : 0;
}
