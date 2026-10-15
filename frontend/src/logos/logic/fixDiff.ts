// What a fix changes, word by word: the words the quote and the replacement
// share at either end, and the stretch between that actually differs. Enough
// to show "lifted the ~~teapot~~ **kettle** and poured" without a diff library.
//
// Words are compared without the space that follows them, so "Winter" at the
// end of one phrase and "Winter " mid-way through the other still match.

export interface FixDiff {
  before: string;
  removed: string;
  added: string;
  after: string;
}

const words = (text: string) => text.match(/\S+\s*/g) ?? [];
const same = (a: string | undefined, b: string | undefined) =>
  a?.trimEnd() === b?.trimEnd();

export function fixDiff(quote: string, replacement: string): FixDiff {
  const a = words(quote);
  const b = words(replacement);
  let start = 0;
  while (start < a.length && start < b.length && same(a[start], b[start])) start += 1;
  let end = 0;
  while (
    end < a.length - start &&
    end < b.length - start &&
    same(a[a.length - 1 - end], b[b.length - 1 - end])
  ) {
    end += 1;
  }
  return {
    before: a.slice(0, start).join(""),
    removed: a.slice(start, a.length - end).join(""),
    added: b.slice(start, b.length - end).join(""),
    after: a.slice(a.length - end).join(""),
  };
}
