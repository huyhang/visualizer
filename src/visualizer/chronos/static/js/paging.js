// One paginator, shared by every table that has one.
//
// Filtering, ordering and paging all happen server-side, so a table never holds
// more than the page it is showing: this needs nothing but the counts the
// browse endpoints already return, and a callback. Pure render, no fetching —
// which is what keeps the plotline table and the scene library from drifting
// into two subtly different pagers, the way the two copies of `slugify` did.

import { el } from "./dom.js";

// `data` is any browse response: { page, pages, total }. `noun` names what is
// being counted, singularised for a count of one.
export function pager({ page, pages, total }, onPage, { noun = "row" } = {}) {
  return el("div", { class: "pager" }, [
    el("button", {
      class: "btn secondary sm", text: "‹ Prev",
      disabled: page <= 1 ? "" : null, onclick: () => onPage(page - 1),
    }),
    el("span", {
      class: "pager-info",
      text: `Page ${page} of ${pages} · ${total} ${noun}${total === 1 ? "" : "s"}`,
    }),
    el("button", {
      class: "btn secondary sm", text: "Next ›",
      disabled: page >= pages ? "" : null, onclick: () => onPage(page + 1),
    }),
  ]);
}
