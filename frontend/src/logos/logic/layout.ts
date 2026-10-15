// When the writing page gives up three columns for drawers.
//
// Outline 15rem, tools 21.5rem, and the prose at least 28rem between them:
// below 64.5rem of workspace the two panels become drawers. Measured in rem,
// so the shared text-size setting moves the switch with it -- at a larger
// size the page goes to drawers sooner rather than squeezing the prose.

export const DRAWERS_BELOW_REM = 64.5;

/** Whether a workspace `width` pixels wide, at `rem` pixels per rem, uses drawers. */
export function usesDrawers(width: number, rem: number): boolean {
  return rem > 0 && width / rem < DRAWERS_BELOW_REM;
}

export interface ViewportMetrics {
  /** The window's layout viewport, as `window.innerWidth` and `innerHeight`. */
  innerWidth: number;
  innerHeight: number;
  /** The visual viewport, as `window.visualViewport` gives it. */
  width: number;
  height: number;
  offsetTop: number;
  scale: number;
}

/**
 * How many CSS pixels at the foot of the window a phone's on-screen keyboard
 * covers: what the visual viewport has given up below it. Nothing while the
 * page is pinched in, or laid out wider than the screen -- then the two
 * viewports differ for reasons that are not a keyboard.
 */
export function keyboardCover(m: ViewportMetrics): number {
  if (Math.abs(m.scale - 1) > 0.01 || m.innerWidth - m.width > 1) return 0;
  return Math.max(0, Math.round(m.innerHeight - m.height - m.offsetTop));
}
