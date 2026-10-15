// Where a menu of a given size fits, given where the pointer was.

const EDGE = 8;

export interface Point {
  x: number;
  y: number;
}

export interface Size {
  width: number;
  height: number;
}

export function menuPosition(
  pointer: Point,
  menu: Size,
  viewport: Size,
): { left: number; top: number } {
  return {
    left: Math.max(EDGE, Math.min(pointer.x, viewport.width - menu.width - EDGE)),
    top: Math.max(EDGE, Math.min(pointer.y, viewport.height - menu.height - EDGE)),
  };
}
