import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(() => {
  cleanup();
  window.location.hash = "";
  window.localStorage.clear();
});

// jsdom has neither; Radix and the layout hook ask for them.
if (!window.matchMedia) {
  window.matchMedia = (query: string) =>
    ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    }) as MediaQueryList;
}
if (!window.ResizeObserver) {
  window.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}

// Layout jsdom does not do, which ProseMirror asks for when it scrolls or
// measures the selection: an empty rectangle is an honest answer here.
const emptyRect = () => new DOMRect(0, 0, 0, 0);
const emptyRects = () => Object.assign([], { item: () => null }) as unknown as DOMRectList;
if (!Range.prototype.getBoundingClientRect)
  Range.prototype.getBoundingClientRect = emptyRect;
if (!Range.prototype.getClientRects) Range.prototype.getClientRects = emptyRects;
if (!Element.prototype.scrollIntoView) Element.prototype.scrollIntoView = () => {};
if (!document.elementFromPoint) document.elementFromPoint = () => null;
// Pointer capture, which Radix's swipeable toasts use.
if (!Element.prototype.hasPointerCapture) Element.prototype.hasPointerCapture = () => false;
if (!Element.prototype.setPointerCapture) Element.prototype.setPointerCapture = () => {};
if (!Element.prototype.releasePointerCapture)
  Element.prototype.releasePointerCapture = () => {};
