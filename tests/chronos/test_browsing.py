"""Unit tests for the pure plotline-browser helpers (no DB, no Flask)."""

from visualizer.chronos.browsing import (
    DEFAULT_PER_PAGE,
    MAX_PER_PAGE,
    browse_plotlines,
    clamp_per_page,
    matches_all_words,
    searchable_text,
)


def row(id_, name=None, goals=(), event_titles=(), book="ember-pact"):
    return {
        "id": id_,
        "book": book,
        "name": name,
        "goals": list(goals),
        "event_titles": list(event_titles),
    }


# -- searchable text / matching ----------------------------------------------


def test_searchable_text_combines_name_goals_and_event_titles():
    r = row("kr", name="Knight's Road", goals=["Deliver Seal"], event_titles=["Aldric Departs"])
    text = searchable_text(r)
    assert "knight's road" in text
    assert "deliver seal" in text
    assert "aldric departs" in text


def test_searchable_text_falls_back_to_id_when_unnamed():
    assert "knights-road" in searchable_text(row("knights-road"))


def test_empty_query_matches_everything():
    assert matches_all_words(row("kr", name="Knight's Road"), "") is True
    assert matches_all_words(row("kr", name="Knight's Road"), "   ") is True


def test_all_words_must_be_present():
    r = row("kr", name="Knight's Road", event_titles=["Aldric Departs"])
    assert matches_all_words(r, "knight aldric") is True   # both present
    assert matches_all_words(r, "knight lyra") is False    # 'lyra' absent


def test_matching_is_case_insensitive_and_substring():
    assert matches_all_words(row("kr", name="Emberport"), "EMB") is True


# -- per-page clamping -------------------------------------------------------


def test_clamp_per_page_defaults_and_bounds():
    assert clamp_per_page(None) == DEFAULT_PER_PAGE
    assert clamp_per_page(0) == DEFAULT_PER_PAGE
    assert clamp_per_page(-5) == DEFAULT_PER_PAGE
    assert clamp_per_page(5) == 5
    assert clamp_per_page(10_000) == MAX_PER_PAGE


# -- browse (filter + sort + paginate) ---------------------------------------


def test_ordered_by_name_case_insensitively():
    rows = [row("c", name="charlie"), row("a", name="Alpha"), row("b", name="beta")]
    out = browse_plotlines(rows)
    assert [p["name"] for p in out["plotlines"]] == ["Alpha", "beta", "charlie"]


def test_untitled_plotlines_sort_by_id():
    rows = [row("zeta"), row("alpha")]
    out = browse_plotlines(rows)
    assert [p["name"] for p in out["plotlines"]] == ["alpha", "zeta"]


def test_filter_narrows_results():
    rows = [
        row("kr", name="Knight's Road"),
        row("ss", name="Spy's Shadow"),
        row("mg", name="Magister's Gambit"),
    ]
    out = browse_plotlines(rows, query="spy")
    assert [p["id"] for p in out["plotlines"]] == ["ss"]
    assert out["total"] == 1


def test_pagination_slices_and_reports_totals():
    rows = [row(f"p{i:02d}", name=f"Plot {i:02d}") for i in range(25)]
    page1 = browse_plotlines(rows, page=1, per_page=10)
    assert len(page1["plotlines"]) == 10
    assert page1["total"] == 25 and page1["pages"] == 3 and page1["page"] == 1
    assert page1["plotlines"][0]["name"] == "Plot 00"

    page3 = browse_plotlines(rows, page=3, per_page=10)
    assert len(page3["plotlines"]) == 5
    assert page3["plotlines"][0]["name"] == "Plot 20"


def test_out_of_range_page_is_clamped_not_error():
    rows = [row("a", name="a"), row("b", name="b")]
    out = browse_plotlines(rows, page=99, per_page=10)
    assert out["page"] == 1  # clamped to the only page
    assert [p["id"] for p in out["plotlines"]] == ["a", "b"]


def test_empty_input_yields_one_empty_page():
    out = browse_plotlines([], page=1, per_page=10)
    assert out == {"plotlines": [], "page": 1, "per_page": 10, "total": 0, "pages": 1}


def test_presented_rows_drop_filter_only_fields():
    rows = [row("kr", name="Knight's Road", goals=["Deliver Seal"], event_titles=["Aldric Departs"])]
    out = browse_plotlines(rows)
    assert out["plotlines"][0] == {
        "id": "kr",
        "book": "ember-pact",
        "name": "Knight's Road",
        "goals": ["Deliver Seal"],
    }
