// The Writing Coach panel: findings in, cards out.
//
// It knows nothing about contenteditable, the API or localStorage. Everything
// it touches arrives as a small injected seam -- including the element
// builders, the same way `prose.js` takes a node factory -- so the whole
// panel, applying a suggestion and undoing it included, can be driven from a
// test with plain objects and no browser.

import { el as browserEl, fill as browserFill } from "./dom.js";

const DIALECTS = [["en-US", "US"], ["en-GB", "UK"]];

export function createCoachPanel({
  body, requestReview, preferences, prose,
  ui = { el: browserEl, fill: browserFill },
}) {
  const { el, fill } = ui;
  function dialectPicker(rerender) {
    return el("label", { class: "coach-dialect" }, [
      el("span", { text: "English" }),
      el("select", {
        onchange: (event) => {
          preferences.setDialect(event.target.value);
          rerender();
        },
      }, DIALECTS.map(([value, text]) => el("option", {
        value, text, selected: preferences.dialect() === value,
      }))),
    ]);
  }

  function applyAction(issue, card, rerender) {
    return el("button", {
      class: "btn sm", type: "button", text: `Use “${issue.replacement}”`,
      onclick: () => {
        const before = prose.snapshot();
        if (!prose.replaceIn(issue.block, issue.excerpt, issue.replacement)) return;
        fill(card, [
          el("p", { text: "Suggestion applied." }),
          el("button", {
            class: "btn ghost sm", type: "button", text: "Undo",
            onclick: () => { prose.restore(before); rerender(); },
          }),
        ]);
      },
    });
  }

  function issueCard(issue, rerender) {
    const card = el("article", { class: "coach-issue" });
    fill(card, [
      el("small", { text: issue.category }),
      el("strong", { text: issue.title }),
      el("p", { text: issue.message }),
      el("q", { text: issue.excerpt }),
      el("div", { class: "coach-actions" }, [
        issue.replacement !== null ? applyAction(issue, card, rerender) : null,
        el("button", {
          class: "btn ghost sm", type: "button", text: "Show",
          onclick: () => prose.reveal(issue.block),
        }),
        el("button", {
          class: "btn ghost sm", type: "button", text: "Dismiss",
          onclick: () => card.remove(),
        }),
        el("button", {
          class: "btn ghost sm", type: "button", text: "Ignore rule",
          onclick: () => { preferences.ignore(issue.title); card.remove(); },
        }),
      ]),
    ]);
    return card;
  }

  async function review() {
    fill(body, [el("p", { class: "muted", text: "Reviewing locally..." })]);
    try {
      const result = await requestReview(preferences.dialect());
      const picker = dialectPicker(review);
      const issues = (result.issues || [])
        .filter((issue) => !preferences.isIgnored(issue.title));
      fill(body, issues.length
        ? [picker, ...issues.map((issue) => issueCard(issue, review))]
        : [picker, el("p", {
          class: "coach-clear", text: "No local suggestions. Keep writing.",
        })]);
    } catch (error) {
      fill(body, [el("p", {
        class: "form-error", text: (error && error.message) || "Review failed.",
      })]);
    }
  }

  return { review };
}
