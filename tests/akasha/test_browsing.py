"""Unit tests for the pure browse/suggest helpers."""

from visualizer.akasha.browsing import (
    DEFAULT_PER_PAGE,
    MAX_PER_PAGE,
    browse_articles,
    can_delete_collection,
    can_write_in_collection,
    clamp_per_page,
    matches_all_words,
    most_recent,
    rank_suggestions,
    visible_collections,
    visible_databases,
)


def grant(database=None, collection=None, doc_id=None, perms=("read",)):
    return {"database": database, "collection": collection, "doc_id": doc_id, "perms": list(perms)}


def test_wildcard_grant_sees_all_databases():
    grants = [grant()]  # database=None -> any
    assert visible_databases(grants, ["a", "b"]) == ["a", "b"]


def test_database_grant_scopes_visibility():
    grants = [grant(database="earth")]
    assert visible_databases(grants, ["earth", "mars"]) == ["earth"]


def test_doc_level_grant_makes_its_database_visible():
    grants = [grant(database="earth", collection="lotr", doc_id="aragorn")]
    assert visible_databases(grants, ["earth", "mars"]) == ["earth"]


def test_write_only_grant_does_not_grant_read_visibility():
    grants = [grant(database="earth", perms=("write",))]
    assert visible_databases(grants, ["earth"]) == []


def test_visible_collections_scopes_by_database_and_collection():
    grants = [grant(database="earth", collection="lotr")]
    assert visible_collections(grants, "earth", ["lotr", "hobbit"]) == ["lotr"]
    assert visible_collections(grants, "mars", ["lotr"]) == []


def test_collection_wildcard_in_database():
    grants = [grant(database="earth")]  # whole database
    assert visible_collections(grants, "earth", ["lotr", "hobbit"]) == ["lotr", "hobbit"]


def test_rank_suggestions_nearest_scope_first():
    items = [
        {"slug": "far", "title": "Far", "database": "other", "collection": "x"},
        {"slug": "same-col", "title": "SameCol", "database": "earth", "collection": "lotr"},
        {"slug": "same-db", "title": "SameDb", "database": "earth", "collection": "hobbit"},
    ]
    ranked = rank_suggestions(items, current_db="earth", current_col="lotr")
    assert [r["slug"] for r in ranked] == ["same-col", "same-db", "far"]


def test_rank_suggestions_ties_break_on_title():
    items = [
        {"slug": "b", "title": "Beta", "database": "d", "collection": "c"},
        {"slug": "a", "title": "Alpha", "database": "d", "collection": "c"},
    ]
    ranked = rank_suggestions(items)
    assert [r["title"] for r in ranked] == ["Alpha", "Beta"]


# -- "may I add to this?" ----------------------------------------------------


def test_collection_grant_permits_a_new_article():
    grants = [grant(database="earth", collection="lotr", perms=("read", "write"))]
    assert can_write_in_collection(grants, "earth", "lotr") is True


def test_document_grant_does_not_permit_a_new_article():
    """Being allowed to edit one article is not permission to invent another."""
    grants = [grant(database="earth", collection="lotr", doc_id="aragorn",
                    perms=("read", "write", "delete"))]
    assert can_write_in_collection(grants, "earth", "lotr") is False
    assert can_delete_collection(grants, "earth", "lotr") is False


def test_ownership_of_a_collection_is_holding_delete_on_it():
    grants = [grant(database="earth", collection="lotr",
                    perms=("read", "write", "delete"))]
    assert can_delete_collection(grants, "earth", "lotr") is True


# -- the article list --------------------------------------------------------


def row(id, title=None, fields=(), updated=None):
    return {"id": id, "title": title, "fields": list(fields), "updated": updated}


ROWS = [
    row("frodo", "Frodo", ["Hobbit", "the Shire"], updated="2024-03-02T00:00:00"),
    row("aragorn", "Aragorn", ["Man", "Heir of Isildur"], updated="2024-03-01T00:00:00"),
    row("nameless", None, ["a wandering thing"], updated="2024-03-03T00:00:00"),
]


def test_blank_filter_matches_everything():
    assert matches_all_words(ROWS[0], "   ") is True


def test_filter_reaches_the_article_body_not_just_the_title():
    assert matches_all_words(ROWS[1], "isildur") is True


def test_filter_requires_every_word_and_ignores_case():
    assert matches_all_words(ROWS[1], "ARA man") is True
    assert matches_all_words(ROWS[1], "aragorn hobbit") is False


def test_articles_are_ordered_by_title_falling_back_to_id():
    ids = [d["id"] for d in browse_articles(ROWS)["documents"]]
    assert ids == ["aragorn", "frodo", "nameless"]


def test_filter_only_text_is_dropped_from_the_result():
    assert all("fields" not in d for d in browse_articles(ROWS)["documents"])


def test_paging_reports_totals():
    page = browse_articles(ROWS, page=1, per_page=2)
    assert (page["total"], page["pages"], page["page"]) == (3, 2, 1)
    assert [d["id"] for d in page["documents"]] == ["aragorn", "frodo"]


def test_out_of_range_page_clamps_to_the_last_one():
    """The filter narrowing under someone on page 4 should not be an error."""
    page = browse_articles(ROWS, page=99, per_page=2)
    assert page["page"] == 2
    assert [d["id"] for d in page["documents"]] == ["nameless"]


def test_an_empty_result_still_has_one_page():
    page = browse_articles(ROWS, query="orcs")
    assert (page["documents"], page["total"], page["pages"]) == ([], 0, 1)


def test_per_page_is_bounded():
    assert clamp_per_page(None) == DEFAULT_PER_PAGE
    assert clamp_per_page(0) == DEFAULT_PER_PAGE
    assert clamp_per_page(-5) == DEFAULT_PER_PAGE
    assert clamp_per_page(10_000) == MAX_PER_PAGE


# -- recently edited ---------------------------------------------------------


def test_most_recent_is_newest_first_and_capped():
    assert [d["id"] for d in most_recent(ROWS, 2)] == ["nameless", "frodo"]


def test_a_row_with_no_history_sorts_last():
    rows = [*ROWS, row("ancient", "Ancient")]
    assert most_recent(rows, 4)[-1]["id"] == "ancient"
