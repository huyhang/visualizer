"""The research, review and discussion pipelines, against a scripted model and
a fake web.

The model here is a stand-in that answers each step from a script, so these
tests pin down what the pipelines *do with* model output -- which is where the
design's rules live -- not how good a real model is (see the smoke test notes
in docs/gpu_worker/README.md for that).
"""

import copy

import pytest

from tests.gpubox.spec import validator
from visualizer.gpu_worker.discussion import DiscussionPipeline
from visualizer.gpu_worker.models import SearchHit
from visualizer.gpu_worker.pipelines import (
    ModelOutputError,
    NoSources,
    PipelineUnavailable,
)
from visualizer.gpu_worker.research import ResearchPipeline, compose_body
from visualizer.gpu_worker.review import PART_CHARS, ReviewPipeline

from .conftest import Clock, StubFetcher

QUESTION = "Song-dynasty tea culture"
SECRET_TITLE = "The Traitor of Highkeep"


def page(title, *paragraphs, figure=None, lang="en", license_=None):
    head = f'<link rel="license" href="{license_}">' if license_ else ""
    fig = (f'<figure><img src="{figure[0]}"><figcaption>{figure[1]}</figcaption>'
           f'</figure>') if figure else ""
    body = "".join(f"<p>{p}</p>" for p in paragraphs)
    return (f'<html lang="{lang}"><head><title>{title}</title>{head}</head>'
            f'<body>{body}{fig}</body></html>').encode(), "text/html"


FILLER = "Contemporary accounts describe the practice in detail. " * 10
WEB = {
    "https://museum.example/tea": page(
        "Song tea", "Tea was ground to powder and whisked into a froth in the bowl.",
        FILLER, figure=("https://museum.example/bowl.jpg", "Jian ware tea bowl"),
        license_="CC0"),
    "https://encyclopedia.example/ming": page(
        "Ming tea", "Loose-leaf steeping became the norm only in the Ming dynasty.",
        FILLER),
    "https://stub.example/": page("Stub", "Too short."),
}


class ScriptedModel:
    """OllamaClient's surface, answering by which step is asking."""

    def __init__(self, **handlers):
        self.handlers = handlers
        self.calls = []
        self.loaded_models = ["qwen3:30b"]
        self.loads = []

    def loaded(self):
        return list(self.loaded_models)

    def load(self, model):
        self.loads.append(model)

    def chat_json(self, model, messages, schema, **options):
        system = messages[0]["content"]
        step = next(name for name, marker in (
            ("plan", "You plan web searches"), ("extract", "You extract facts"),
            ("write", "You write a short"), ("review", "You are a careful fiction"),
            ("discuss", "You are the fiction editor who raised"),
        ) if system.startswith(marker))
        self.calls.append((step, messages))
        return self.handlers[step](messages[-1]["content"])


class Search:
    def __init__(self, results):
        self.results = results
        self.queries = []

    def search(self, query, *, language=None):
        self.queries.append((query, language))
        return [SearchHit(url=u, title="", snippet="") for u in self.results]


class Checker:
    research_model, review_model = "bespoke-minicheck", "gemma3:27b"

    def __init__(self, up=True, rejects=(), dies=False):
        self._up, self.rejects, self.dies = up, rejects, dies
        self.asked = []

    def up(self):
        return self._up

    def supports(self, claim, evidence):
        self.asked.append(claim)
        if self.dies:
            raise PipelineUnavailable("The second checker is not responding")
        return not any(word in claim for word in self.rejects)

    def confirms(self, issue, passage, reference):
        self.asked.append(issue)
        if self.dies:
            raise PipelineUnavailable("The second checker is not responding")
        return not any(word in issue for word in self.rejects)


class Ctx:
    def __init__(self):
        self.stages = []

    def progress(self, stage, message=None):
        self.stages.append(stage)


def extract_from(page_text):
    """A model that quotes exactly, paraphrases once, and forgets a quote once."""
    if "Tea was ground" in page_text:
        return {"facts": [
            {"text": "Song tea was powdered and whisked.",
             "quote": "Tea was ground to powder and whisked into a froth in the bowl."},
            {"text": "Tea was beaten in a cup.",
             "quote": "The tea was beaten energetically in a cup."},    # not on page
            {"text": "Whisking was done at court.", "quote": ""}]}
    if "Loose-leaf" in page_text:
        return {"facts": [{"text": "Steeping loose leaves came later, in the Ming.",
                           "quote": "Loose-leaf steeping became the norm only in "
                                    "the Ming dynasty."}]}
    return {"facts": []}


def research_model(**overrides):
    handlers = {
        "plan": lambda _: {"queries": [{"q": "song dynasty tea whisking",
                                        "language": "en"},
                                       {"q": "宋代 点茶", "language": "zh"}]},
        "extract": extract_from,
        "write": lambda _: {
            "title": "Song-Dynasty Tea Culture",
            "overview": "Tea was whisked [[cite:s1]]. It was also sung to [[cite:s9]].",
            "topic": "food", "era": "Northern Song",
            "links": ["song-dynasty/research/song-tea-bowls", "invented/ref/x"]},
    }
    handlers.update(overrides)
    return ScriptedModel(**handlers)


REQUEST = {"question": QUESTION, "languages": ["en", "zh"], "max_sources": 3,
           "include_images": True, "known_articles": [
               {"ref": "song-dynasty/research/song-tea-bowls", "title": "Song tea bowls"},
               {"ref": "ember/characters/corwin", "title": SECRET_TITLE}]}


def run_research(model=None, verifier=None, request=None, results=None, web=None):
    model = model or research_model()
    search = Search(results if results is not None else
                    ["https://museum.example/tea", "https://missing.example/",
                     "https://stub.example/", "https://encyclopedia.example/ming"])
    pipeline = ResearchPipeline(model, search, StubFetcher(web or WEB), verifier,
                                model="qwen3:30b", clock=Clock())
    ctx = Ctx()
    result = pipeline.run(copy.deepcopy(request or REQUEST), ctx)
    return result, model, search, ctx


def signed(result):
    """What the runner adds before the contract check."""
    for candidate in result["article"]["image_candidates"]:
        candidate["fetch_token"] = "t" * 43
    return result


# -- research ----------------------------------------------------------------


def test_a_research_job_end_to_end():
    result, _, _, ctx = run_research()
    validator("ResearchResult").validate(signed(result))
    facts = result["article"]["facts"]
    assert [f["text"] for f in facts] == ["Song tea was powdered and whisked.",
                                          "Steeping loose leaves came later, in the Ming."]
    assert {(d["text"], d["reason"]) for d in result["dropped_facts"]} == {
        ("Tea was beaten in a cup.", "quote_not_found"),
        ("Whisking was done at court.", "no_citation")}
    assert ctx.stages[:2] == ["planning", "searching"]
    assert ctx.stages[-1] == "writing"


def test_every_kept_quote_is_on_its_page():
    result, _, _, _ = run_research()
    sources = {s["key"]: s for s in result["sources"]}
    for fact in result["article"]["facts"]:
        for citation in fact["citations"]:
            assert citation["quote"] in sources[citation["source"]]["excerpts"]


def test_the_planner_sees_the_question_and_nothing_of_the_world():
    _, model, search, _ = run_research()
    plan_messages = next(m for step, m in model.calls if step == "plan")
    sent = " ".join(m["content"] for m in plan_messages)
    assert QUESTION in sent and SECRET_TITLE not in sent and "corwin" not in sent
    assert search.queries == [("song dynasty tea whisking", "en"), ("宋代 点茶", "zh")]
    for step, messages in model.calls:
        if step != "write":
            assert SECRET_TITLE not in str(messages), f"{step} saw the world's titles"


def test_the_draft_cannot_cite_or_link_what_it_was_not_given():
    result, _, _, _ = run_research()
    body = result["article"]["body"]
    assert "[[cite:s9]]" not in body and "[[cite:s1]]" in body
    assert result["article"]["links"] == ["song-dynasty/research/song-tea-bowls"]
    assert "== Key facts ==" in body
    for fact in result["article"]["facts"]:
        assert fact["text"] in body, "every verified fact is listed in the draft"


@pytest.mark.parametrize("written,expected", [
    ("Whisked [[s1]].", "Whisked [[cite:s1]]."),          # seen from a real model
    ("Whisked [s1] (s2) [cite:s1].", "Whisked [[cite:s1]] [[cite:s2]] [[cite:s1]]."),
    ("Whisked [[s7]].", "Whisked."),                       # not a source it was given
])
def test_citation_spellings_are_normalised(written, expected):
    facts = [{"text": "F", "citations": [{"source": "s1", "quote": "q"}],
              "check": {"status": "unchecked"}}]
    body = compose_body(written, facts, cited={"s1", "s2"})
    assert body.split("\n\n")[0] == expected


def test_only_cited_pages_become_sources_and_offer_images():
    result, _, _, _ = run_research()
    assert [s["url"] for s in result["sources"]] == ["https://museum.example/tea",
                                                     "https://encyclopedia.example/ming"]
    assert result["sources"][0]["language"] == "en"
    (candidate,) = result["article"]["image_candidates"]
    assert candidate == {"url": "https://museum.example/bowl.jpg", "source": "s1",
                         "caption": "Jian ware tea bowl", "license": "CC0"}


def test_no_images_unless_asked():
    result, _, _, _ = run_research(request={**REQUEST, "include_images": False})
    assert result["article"]["image_candidates"] == []


def test_a_useless_plan_falls_back_to_the_question():
    _, _, search, _ = run_research(model=research_model(plan=lambda _: {"queries": []}))
    assert search.queries == [(QUESTION, "en")]


@pytest.mark.parametrize("results,web,extract", [
    ([], WEB, extract_from),                                   # nothing found
    (["https://missing.example/", "https://stub.example/"], WEB, extract_from),
    (["https://museum.example/tea"], WEB, lambda _: {"facts": [
        {"text": "Invented.", "quote": "words the page never said at all"}]}),
])
def test_nothing_usable_is_no_sources(results, web, extract):
    with pytest.raises(NoSources):
        run_research(model=research_model(extract=extract), results=results, web=web)


def test_a_cold_model_is_loaded_first():
    model = research_model()
    model.loaded_models = []
    _, _, _, ctx = run_research(model=model)
    assert ctx.stages[0] == "loading_model" and model.loads == ["qwen3:30b"]


# -- the second check, in research -------------------------------------------


def test_the_second_check_runs_before_writing_and_removes_unsupported_facts():
    result, _, _, ctx = run_research(verifier=Checker(rejects=("Ming",)))
    validator("ResearchResult").validate(signed(result))
    assert ctx.stages.index("second_check") < ctx.stages.index("writing")
    assert [f["check"]["status"] for f in result["article"]["facts"]] == ["supported"]
    assert ("Steeping loose leaves came later, in the Ming.", "unsupported") in {
        (d["text"], d["reason"]) for d in result["dropped_facts"]}
    assert result["verification"] == {"status": "checked", "model": "bespoke-minicheck",
                                      "reason": None, "checked": 2, "removed": 1}
    assert "Ming" not in result["article"]["body"]


@pytest.mark.parametrize("verifier,verify,status,reason", [
    (Checker(up=False), "auto", "skipped", "verifier_unavailable"),
    (Checker(dies=True), "auto", "skipped", "verifier_unavailable"),
    (None, "auto", "off", "not_configured"),
    (Checker(), "off", "off", "caller_off"),
])
def test_without_a_second_check_results_say_why(verifier, verify, status, reason):
    result, _, _, _ = run_research(verifier=verifier,
                                   request={**REQUEST, "verify": verify})
    assert (result["verification"]["status"], result["verification"]["reason"]) == \
        (status, reason)
    assert {f["check"]["status"] for f in result["article"]["facts"]} == {"unchecked"}


@pytest.mark.parametrize("verifier", [None, Checker(up=False)])
def test_a_required_second_check_fails_before_any_work(verifier):
    model = research_model()
    with pytest.raises(PipelineUnavailable):
        run_research(model=model, verifier=verifier,
                     request={**REQUEST, "verify": "required"})
    assert model.calls == []


def test_a_search_outage_fails_the_job_as_unavailable():
    class Down(Search):
        def search(self, query, *, language=None):
            raise PipelineUnavailable("Web search (SearXNG) is not responding")

    pipeline = ResearchPipeline(research_model(), Down([]), StubFetcher(WEB), None,
                                model="qwen3:30b")
    with pytest.raises(PipelineUnavailable, match="SearXNG"):
        pipeline.run(copy.deepcopy(REQUEST), Ctx())


# -- review ------------------------------------------------------------------

BLOCKS = [{"id": "b1", "text": "Lin Qingyu lifted the teapot and poured."},
          {"id": "b2", "text": "Her grey eyes narrowed as the paper lanterns rose."},
          {"id": "b3", "text": "She very quickly ran quickly to the gate."}]
REFERENCES = [
    {"ref": "ember/characters/lin", "kind": "canon", "title": "Lin Qingyu",
     "text": "Lin Qingyu has brown eyes."},
    {"ref": "song/research/tea", "kind": "research", "title": "Song tea",
     "text": "Song tea was whisked in bowls; teapots came in the Ming."},
    {"ref": "ember/deviations/lanterns", "kind": "deviation", "title": "Qi lanterns",
     "text": "Paper lanterns float by qi."},
]
REVIEW = {"chapter": {"title": "Chapter 7", "blocks": BLOCKS}, "references": REFERENCES,
          "dialect": "en-GB", "checks": ["continuity", "anachronism", "prose"]}


def issue(check, block, quote, reference="", message="A problem.", **extra):
    return {"check": check, "severity": "warning", "confidence": "likely",
            "block": block, "quote": quote, "message": message,
            "suggestion": "Fix it.", "reference": reference, **extra}


MODEL_ISSUES = [
    issue("anachronism", "b1", "lifted the teapot", "song/research/tea"),
    issue("continuity", "b2", "grey eyes", "ember/characters/lin"),
    issue("anachronism", "b2", "paper lanterns rose", "ember/deviations/lanterns"),
    issue("prose", "b3", "very quickly ran quickly", "song/research/tea"),
    issue("prose", "b3", "very quickly ran quickly", ""),                # duplicate
    issue("continuity", "b1", "words not in the block", "ember/characters/lin"),
    issue("continuity", "b9", "anything", "ember/characters/lin"),     # no such block
    issue("continuity", "b1", "Lin Qingyu", "invented/ref"),           # unknown ref
    issue("tone", "b1", "Lin Qingyu", ""),                             # not a check
]


def run_review(issues=None, verifier=None, request=None, model=None):
    model = model or ScriptedModel(review=lambda _: {"issues": copy.deepcopy(
        MODEL_ISSUES if issues is None else issues)})
    pipeline = ReviewPipeline(model, verifier, model="qwen3:30b", clock=Clock())
    ctx = Ctx()
    return pipeline.run(copy.deepcopy(request or REVIEW), ctx), model, ctx


def test_a_review_keeps_only_issues_that_follow_the_rules():
    result, _, _ = run_review()
    validator("ReviewResult").validate(result)
    kept = {(i["check"], i["block"], i["quote"], i["reference"]) for i in result["issues"]}
    assert kept == {
        ("anachronism", "b1", "lifted the teapot", "song/research/tea"),
        ("continuity", "b2", "grey eyes", "ember/characters/lin"),
        ("prose", "b3", "very quickly ran quickly", None),
    }
    assert all(i["verified"] is None for i in result["issues"])


@pytest.mark.parametrize("given,kept", [
    ("whisked the tea in her bowl", "whisked the tea in her bowl"),
    ('  "whisked the tea in her bowl."  ', "whisked the tea in her bowl"),
    ("lifted the teapot", None),          # the quote itself is no fix
    ("", None),
    (None, None),
])
def test_a_replacement_is_kept_only_when_it_rewords_the_quote(given, kept):
    result, _, _ = run_review(issues=[
        issue("anachronism", "b1", "lifted the teapot", "song/research/tea",
              replacement=given)])
    validator("ReviewResult").validate(result)
    assert result["issues"][0]["replacement"] == kept


def test_the_model_is_asked_for_the_exact_replacement():
    _, model, _ = run_review()
    assert '"replacement" (the exact words to put in place of the quote' \
        in model.calls[0][1][0]["content"]


def test_a_deviation_is_never_reported_against():
    result, _, _ = run_review()
    assert not any("lanterns" in i["quote"] for i in result["issues"])


def test_only_the_checks_asked_for():
    result, _, _ = run_review(request={**REVIEW, "checks": ["prose"]})
    assert {i["check"] for i in result["issues"]} == {"prose"}


def test_a_long_chapter_is_read_in_parts_each_with_only_its_own_blocks():
    blocks = [{"id": f"b{n}", "text": f"Block {n}. " + "x" * 9000} for n in range(1, 6)]
    model = ScriptedModel(review=lambda content: {"issues": [
        issue("prose", "b1", "Block 1"), issue("prose", "b5", "Block 5")]})
    result, model, ctx = run_review(model=model, request={**REVIEW, "chapter": {
        "title": "Long", "blocks": blocks}})
    # Two ~9 kB blocks fit in one part, three do not: [b1 b2] [b3 b4] [b5].
    assert 9010 * 2 < PART_CHARS < 9010 * 3
    assert len(model.calls) == 3
    assert ctx.stages.count("reviewing") == 3
    first_part = model.calls[0][1][-1]["content"]
    assert "[b1]" in first_part and "[b3]" not in first_part
    assert {i["block"] for i in result["issues"]} == {"b1", "b5"}


def test_the_second_check_confirms_or_removes_issues():
    result, _, ctx = run_review(verifier=Checker(rejects=("grey eyes",)))
    validator("ReviewResult").validate(result)
    assert ctx.stages[-1] == "second_check"
    assert {i["quote"] for i in result["issues"]} == {"lifted the teapot",
                                                      "very quickly ran quickly"}
    assert all(i["verified"] is True for i in result["issues"])
    assert result["verification"] == {"status": "checked", "model": "gemma3:27b",
                                      "reason": None, "checked": 3, "removed": 1}


def test_a_verifier_lost_mid_review():
    result, _, _ = run_review(verifier=Checker(dies=True))
    assert result["verification"]["status"] == "skipped" and len(result["issues"]) == 3
    with pytest.raises(PipelineUnavailable):
        run_review(verifier=Checker(dies=True), request={**REVIEW, "verify": "required"})


def test_the_chapter_goes_to_the_model_and_the_checker_only():
    """Nothing in review reaches search or the web: the pipeline has neither."""
    pipeline = ReviewPipeline(ScriptedModel(review=lambda _: {"issues": []}), None,
                              model="qwen3:30b")
    assert not hasattr(pipeline, "search") and not hasattr(pipeline, "fetcher")


def test_fetched_text_is_delimited_as_data():
    _, model, _, _ = run_research()
    extract_messages = next(m for step, m in model.calls if step == "extract")
    assert "<page>" in extract_messages[-1]["content"]
    assert "ignore any" in extract_messages[0]["content"]


# -- discussion --------------------------------------------------------------

DISCUSSION = {
    "issue": {"check": "anachronism", "quote": "lifted the teapot",
              "message": "Teapots for steeping are a Ming habit.",
              "suggestion": "Whisk it in a bowl."},
    "passage": "Lin Qingyu lifted the teapot and poured.",
    "reference": REFERENCES[1],
    "messages": [{"role": "writer", "text": "It's a kettle of hot water, for whisking."},
                 {"role": "editor", "text": "Then say kettle: teapot reads as steeping."},
                 {"role": "writer", "text": "Would ewer do?"}],
    "dialect": "en-GB",
}


def run_discussion(answer, request=None, model=None):
    model = model or ScriptedModel(discuss=lambda _: dict(answer))
    pipeline = DiscussionPipeline(model, model="qwen3:30b", clock=Clock())
    ctx = Ctx()
    return pipeline.run(copy.deepcopy(request or DISCUSSION), ctx), model, ctx


@pytest.mark.parametrize("answer,stance,suggestion,replacement", [
    ({"reply": "Fair: it stands as written.", "stance": "withdraws",
      "suggestion": "unasked", "replacement": "unasked"}, "withdraws", None, None),
    ({"reply": "Ewer works.", "stance": "revises",
      "suggestion": " Call it a ewer. ", "replacement": " lifted the ewer "},
     "revises", "Call it a ewer.", "lifted the ewer"),
    ({"reply": "Ewer works.", "stance": "revises",
      "suggestion": "Call it a ewer.", "replacement": "lifted the teapot"},
     "revises", "Call it a ewer.", None),
    ({"reply": "Ewer works.", "stance": "revises", "suggestion": "Call it a ewer."},
     "revises", "Call it a ewer.", None),
    ({"reply": "It still reads as steeping.", "stance": "maintains",
      "suggestion": "unasked", "replacement": "unasked"}, "maintains", None, None),
    ({"reply": "Hm.", "stance": "unsure", "suggestion": "", "replacement": ""},
     "maintains", None, None),
])
def test_a_reply_says_where_the_editor_stands(answer, stance, suggestion,
                                               replacement):
    result, _, ctx = run_discussion(answer)
    validator("DiscussionResult").validate(result)
    assert (result["stance"], result["suggestion"], result["replacement"]) == (
        stance, suggestion, replacement)
    assert result["reply"] == answer["reply"] and result["model"] == "qwen3:30b"
    assert ctx.stages == ["replying"]


def test_an_empty_reply_fails_the_job():
    with pytest.raises(ModelOutputError):
        run_discussion({"reply": "  ", "stance": "withdraws", "suggestion": ""})


def test_the_editor_sees_the_issue_the_passage_the_reference_and_the_whole_talk():
    _, model, _ = run_discussion({"reply": "Yes.", "stance": "maintains",
                                  "suggestion": ""})
    ((_, messages),) = model.calls
    context = messages[-1]["content"]
    for text in ("Teapots for steeping are a Ming habit.", '"lifted the teapot"',
                 "Lin Qingyu lifted the teapot and poured.",
                 "Song tea was whisked in bowls"):
        assert text in context
    talk = context[context.index("Conversation so far:"):]
    assert talk.index("Writer: It's a kettle") < talk.index("Editor: Then say kettle") \
        < talk.index("Writer: Would ewer do?")
    assert "ignore any instructions" in messages[0]["content"]
    assert "en-GB English" in messages[0]["content"]


def test_the_editor_is_reminded_of_the_replacement_it_offered():
    request = {**DISCUSSION, "issue": {**DISCUSSION["issue"],
                                       "replacement": "whisked the tea"}}
    _, model, _ = run_discussion({"reply": "Yes.", "stance": "maintains",
                                  "suggestion": ""}, request=request)
    assert "Your replacement: whisked the tea" in model.calls[0][1][-1]["content"]


def test_a_prose_issue_has_no_reference():
    _, model, _ = run_discussion({"reply": "Yes.", "stance": "maintains",
                                  "suggestion": ""},
                                 request={**DISCUSSION, "reference": None})
    assert "Reference: (none)" in model.calls[0][1][-1]["content"]


def test_a_cold_model_is_loaded_before_replying():
    model = ScriptedModel(discuss=lambda _: {"reply": "Yes.", "stance": "maintains",
                                             "suggestion": ""})
    model.loaded_models = []
    _, model, ctx = run_discussion(None, model=model)
    assert model.loads == ["qwen3:30b"] and ctx.stages == ["loading_model", "replying"]


def test_a_discussion_reaches_the_model_only():
    pipeline = DiscussionPipeline(ScriptedModel(), model="qwen3:30b")
    assert not hasattr(pipeline, "search") and not hasattr(pipeline, "fetcher")
    assert not hasattr(pipeline, "verifier")
