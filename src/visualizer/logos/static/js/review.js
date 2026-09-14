// Pure filtering for the series Review workspace.

const matches = (values, query) => values
  .filter((value) => typeof value === "string")
  .some((value) => value.toLocaleLowerCase().includes(query));

function atLocation(item, location) {
  if (!location || location === "all") return true;
  if (location === "series") return item.scope === "book";
  const [kind, volume, section] = location.split(":");
  if (kind === "volume") return item.volume === volume;
  return kind === "section" && item.volume === volume && item.section === section;
}

export function filterAnnotations(items, {
  query = "", kind = "all", status = "all", location = "all",
} = {}) {
  const wanted = query.trim().toLocaleLowerCase();
  return (items || []).filter((item) => {
    if (!["note", "checklist"].includes(item.kind)) return false;
    if (!atLocation(item, location)) return false;
    if (kind !== "all" && item.kind !== kind) return false;
    if (status === "open" && item.kind === "checklist" && item.done) return false;
    if (status === "completed" && (item.kind !== "checklist" || !item.done)) return false;
    return !wanted || matches(
      [item.text, item.excerpt, item.volume_title, item.section_title, item.draft_name],
      wanted,
    );
  });
}

export function filterIssues(issues, {
  query = "", category = "all", location = "all", ignored = [],
} = {}) {
  const wanted = query.trim().toLocaleLowerCase();
  const hidden = new Set(ignored);
  return (issues || []).filter((issue) => {
    if (!atLocation(issue, location)) return false;
    if (hidden.has(issue.title)) return false;
    if (category !== "all" && issue.category !== category) return false;
    return !wanted || matches([
      issue.title, issue.message, issue.excerpt, issue.volume_title,
      issue.section_title, issue.draft_name,
    ], wanted);
  });
}

export function sectionKindName(issue) {
  if (issue.section_title) return issue.section_title;
  if (issue.section_kind === "chapter") return `Chapter ${issue.section_number}`;
  const kind = issue.section_kind || "section";
  return kind.charAt(0).toUpperCase() + kind.slice(1);
}
