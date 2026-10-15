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
