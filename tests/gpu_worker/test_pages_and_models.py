"""Reading pages, matching quotes, and talking to Ollama and SearXNG."""

import io
import json
import urllib.error

import pytest

from visualizer.gpu_worker.fetch import Fetched
from visualizer.gpu_worker.models import (
    OllamaClient,
    SearxClient,
    Verifier,
    parse_json,
)
from visualizer.gpu_worker.pages import extract, find_quote, normalize
from visualizer.gpu_worker.pipelines import ModelOutputError, PipelineUnavailable

PAGE = """<!doctype html><html lang="en-GB"><head>
<title>Tea | Museum</title><meta property="og:title" content="Song-dynasty tea">
<link rel="license" href="https://creativecommons.org/publicdomain/zero/1.0/">
<base href="https://museum.example/collection/">
<script>var tracking = "do not read me";</script></head><body>
<nav>Home &rsaquo; Collection</nav>
<header>Museum header</header>
<main><h1>Tea in the Song</h1>
<p>Tea was ground to powder and whisked
   into a froth in the bowl.</p>
<p>Loose-leaf steeping became the norm only in the Ming dynasty.</p>
<figure><img src="bowl.jpg" alt=""><figcaption>Jian ware tea bowl, Song dynasty</figcaption></figure>
<img src="icon.png" width="16" height="16" alt="a tiny icon that is decoration">
<img src="data:image/png;base64,AAAA" alt="an inline image that has no address">
<img src="/scroll.jpg" alt="Along the River During the Qingming Festival, detail">
</main><footer>Copyright notice</footer></body></html>"""


def fetched(html, url="https://museum.example/tea", charset="utf-8"):
    return Fetched(url=url, content_type="text/html", charset=charset,
                   body=html.encode(charset or "utf-8"))


# -- pages -------------------------------------------------------------------


def test_a_page_reads_as_its_text_and_nothing_else():
    page = extract(fetched(PAGE))
    assert page.title == "Song-dynasty tea"
    assert page.site == "museum.example"
    assert page.language == "en"
    assert "Tea was ground to powder and whisked into a froth in the bowl." in page.text
    for furniture in ("tracking", "Home", "Museum header", "Copyright"):
        assert furniture not in page.text


def test_captioned_images_are_found_and_decoration_is_not():
    images = {image.url: image.caption for image in extract(fetched(PAGE)).images}
    assert images == {
        "https://museum.example/collection/bowl.jpg": "Jian ware tea bowl, Song dynasty",
        "https://museum.example/scroll.jpg":
            "Along the River During the Qingming Festival, detail",
    }


def test_a_declared_license_is_kept():
    assert extract(fetched(PAGE)).license == \
        "https://creativecommons.org/publicdomain/zero/1.0/"


def test_a_page_in_another_encoding():
    html = ('<html lang="zh"><head><meta charset="gbk"><title>宋代点茶</title></head>'
            '<body><p>宋人饮茶，先将茶叶碾成细末，再以沸水冲点，用茶筅击拂。</p></body></html>')
    page = extract(Fetched(url="https://example.cn/tea", content_type="text/html",
                           charset=None, body=html.encode("gbk")))
    assert page.title == "宋代点茶" and page.language == "zh"
    assert "茶筅击拂" in page.text


@pytest.mark.parametrize("quote", [
    "Tea was ground to powder and whisked into a froth in the bowl.",
    "Tea was ground to powder and whisked\n   into a froth",      # whitespace
    "“Loose-leaf steeping became the norm only in the Ming dynasty.”",  # curly quotes
])
def test_a_quote_is_found_when_it_is_really_there(quote):
    page = extract(fetched(PAGE))
    found = find_quote(quote, page.haystack)
    assert found is not None and found in page.haystack


@pytest.mark.parametrize("quote", [
    "Tea was ground into powder and beaten to a froth.",   # a paraphrase
    "whisked",                                             # too short to be evidence
    "",
    "Tea was ground to powder and whisked into a froth in the cup.",
])
def test_a_quote_that_is_not_there_is_not_found(quote):
    assert find_quote(quote, extract(fetched(PAGE)).haystack) is None


def test_typography_is_folded_not_meaning():
    assert normalize("“It’s — fine” now") == "\"It's - fine\" now"


# -- Ollama ------------------------------------------------------------------


class Server:
    """urlopen standing in for a local service: records requests, scripts replies."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.requests = []

    def __call__(self, request, timeout=None):
        url = request if isinstance(request, str) else request.full_url
        body = None
        if not isinstance(request, str) and request.data:
            body = json.loads(request.data)
        self.requests.append({"url": url, "body": body, "timeout": timeout})
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return io.BytesIO(json.dumps(reply).encode())


def http_error(code, text=""):
    return urllib.error.HTTPError("u", code, "err", {}, io.BytesIO(text.encode()))


def chat_reply(content):
    return {"message": {"role": "assistant", "content": content}}


def test_chat_asks_for_json_without_thinking_in_a_wide_context():
    server = Server(chat_reply('{"ok": true}'))
    client = OllamaClient("http://127.0.0.1:11434", num_ctx=32768, opener=server)
    assert client.chat_json("qwen3:30b", [{"role": "user", "content": "hi"}],
                            {"type": "object"}) == {"ok": True}
    body = server.requests[0]["body"]
    assert body["think"] is False and body["stream"] is False
    assert body["format"] == {"type": "object"}
    assert body["options"]["num_ctx"] == 32768


def test_a_model_that_cannot_think_is_asked_again_plainly():
    server = Server(http_error(400, '{"error":"model does not support thinking"}'),
                    chat_reply("plain"))
    client = OllamaClient("http://127.0.0.1:11434", opener=server)
    assert client.chat("granite4.2:8b", []) == "plain"
    assert "think" not in server.requests[1]["body"]


def test_unparseable_output_is_retried_once_then_fails():
    server = Server(chat_reply("Sure! Here you go"), chat_reply('{"facts": []}'))
    client = OllamaClient("http://x", opener=server)
    assert client.chat_json("m", [], {}) == {"facts": []}
    assert server.requests[1]["body"]["messages"][-1]["content"] == \
        "Answer with valid JSON only."
    failing = OllamaClient("http://x", opener=Server(chat_reply("no"), chat_reply("no")))
    with pytest.raises(ModelOutputError):
        failing.chat_json("m", [], {})


@pytest.mark.parametrize("error,message", [
    (urllib.error.URLError("refused"), "The model server (Ollama) is not responding"),
    (http_error(404, '{"error":"model not found"}'),
     "The model qwen3:30b is not installed on the model server (Ollama)"),
])
def test_ollama_failures_name_the_service(error, message):
    client = OllamaClient("http://x", opener=Server(error))
    with pytest.raises(PipelineUnavailable, match=message.replace("(", r"\(")
                       .replace(")", r"\)")):
        client.chat("qwen3:30b", [])


@pytest.mark.parametrize("text,value", [
    ('<think>hmm</think>{"a": 1}', {"a": 1}),
    ('```json\n{"a": 2}\n```', {"a": 2}),
    ('Here it is: {"a": 3} hope that helps', {"a": 3}),
])
def test_json_is_found_inside_chatter(text, value):
    assert parse_json(text) == value


def test_models_in_memory():
    server = Server({"models": [{"name": "qwen3:30b", "size_vram": 1}]})
    assert OllamaClient("http://x", opener=server).loaded() == ["qwen3:30b"]


# -- SearXNG -----------------------------------------------------------------


def test_search_asks_for_json_and_keeps_only_web_results():
    server = Server({"results": [
        {"url": "https://museum.example/tea", "title": "Tea", "content": "Whisked"},
        {"url": "javascript:alert(1)", "title": "x"},
        {"url": "magnet:?xt=urn", "title": "y"}]})
    hits = SearxClient("http://127.0.0.1:8888", opener=server).search(
        "宋代 点茶", language="zh")
    assert [h.url for h in hits] == ["https://museum.example/tea"]
    url = server.requests[0]["url"]
    assert "format=json" in url and "language=zh" in url


def test_search_failure_names_searxng():
    with pytest.raises(PipelineUnavailable, match="SearXNG"):
        SearxClient("http://x", opener=Server(urllib.error.URLError("x"))).search("q")


# -- the second checker ------------------------------------------------------


def test_minicheck_gets_its_own_prompt_shape_and_yes_means_supported():
    server = Server(chat_reply("Yes"), chat_reply("No"))
    verifier = Verifier(OllamaClient("http://mac", opener=server),
                        "bespoke-minicheck", "gemma3:27b")
    assert verifier.supports("Tea was whisked.", ["the tea was whisked in a bowl"])
    assert not verifier.supports("Tea was steeped.", ["the tea was whisked in a bowl"])
    message = server.requests[0]["body"]["messages"][0]["content"]
    assert message == "Document: the tea was whisked in a bowl\nClaim: Tea was whisked."
