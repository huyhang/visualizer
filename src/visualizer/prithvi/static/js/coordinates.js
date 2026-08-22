// Screen pixels <-> viewBox units. Pure except for reading the SVG's own
// matrix, which is the one thing only the browser can tell us.
//
// Pin positions are stored in the drawing's own coordinate space, so every
// click has to be projected back through whatever zoom and pan are in force.
// Doing it with the live `getScreenCTM()` rather than by tracking a transform
// ourselves means the answer stays right however the drawing got where it is.

export function transformPoint(x, y, matrix) {
  return {
    x: matrix.a * x + matrix.c * y + matrix.e,
    y: matrix.b * x + matrix.d * y + matrix.f,
  };
}

export function clientPoint(svg, clientX, clientY) {
  const matrix = svg.getScreenCTM();
  if (!matrix) return null;
  return transformPoint(clientX, clientY, matrix.inverse());
}

// "Any valid location on the map" is any point inside the declared viewBox --
// the same rectangle the server validates against, so the UI refuses exactly
// what the API would have refused rather than guessing at a smaller box.
export function insideViewBox(point, viewBox) {
  if (!point || !Array.isArray(viewBox) || viewBox.length !== 4) return false;
  const [minX, minY, width, height] = viewBox;
  return (
    point.x >= minX && point.x <= minX + width
    && point.y >= minY && point.y <= minY + height
  );
}
