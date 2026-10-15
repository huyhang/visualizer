// A finding's message quotes Akasha articles by id, because the rules cannot
// see Akasha and the reader may not be allowed to. Once the titles are known,
// `'aldric'` reads `'Sir Aldric'`; without the grant it stays the id, which is
// the honest outcome. Exact match including the quotes, so an id can never
// rewrite part of another word.

export function withTitles(message: string, titles: Map<string, string>): string {
  let out = message;
  for (const [id, title] of titles) {
    if (title && title !== id) out = out.split(`'${id}'`).join(`'${title}'`);
  }
  return out;
}
