"""The worker's two local services: Ollama (models) and SearXNG (search).

Both are reached on localhost only, with short, explicit timeouts. A service
that does not answer raises ``PipelineUnavailable`` naming *which* one -- the
writer sees that message -- never what was being asked of it.

Model output is asked for as JSON with a schema (Ollama's structured outputs),
with thinking switched off: these are extraction and editing tasks, and a
reasoning trace would only spend the context window. Output that still fails
to parse is retried once, then fails the job.
"""

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import urlencode, urlsplit

from .pipelines import ModelOutputError, PipelineUnavailable

_THINKING = re.compile(r"<think>.*?</think>", re.DOTALL)
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$")


def parse_json(text: str):
    """JSON out of a model reply, forgiving a stray reasoning block or fence."""
    cleaned = _FENCE.sub("", _THINKING.sub("", text or "").strip()).strip()
    try:
        return json.loads(cleaned)
    except ValueError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(cleaned[start:end + 1])
            except ValueError:
                pass
    raise ModelOutputError("The model did not answer with valid JSON")


class OllamaClient:
    def __init__(self, base_url: str, *, timeout: float = 300, num_ctx: int = 32768,
                 name: str = "the model server (Ollama)",
                 opener=urllib.request.urlopen):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.num_ctx = num_ctx
        self.name = name
        self._open = opener

    def loaded(self) -> list[str]:
        reply = self._request("GET", "/api/ps", timeout=5)
        return [m.get("name") or m.get("model") for m in reply.get("models") or []]

    def available(self, timeout: float = 3) -> bool:
        try:
            self._request("GET", "/api/tags", timeout=timeout)
            return True
        except PipelineUnavailable:
            return False

    def load(self, model: str) -> None:
        """Load ``model`` into memory: a generate call with no prompt."""
        self._request("POST", "/api/generate", {"model": model})

    def chat(self, model: str, messages: list[dict], *, schema: dict | None = None,
             temperature: float = 0.2) -> str:
        body = {"model": model, "messages": messages, "stream": False, "think": False,
                "options": {"num_ctx": self.num_ctx, "temperature": temperature}}
        if schema is not None:
            body["format"] = schema
        try:
            reply = self._request("POST", "/api/chat", body)
        except _ThinkUnsupported:
            # Older Ollama, or a model with no notion of thinking: ask plainly.
            body.pop("think")
            reply = self._request("POST", "/api/chat", body)
        return (reply.get("message") or {}).get("content", "")

    def chat_json(self, model: str, messages: list[dict], schema: dict,
                  **options) -> dict:
        """A JSON object matching ``schema`` -- retried once if it doesn't parse."""
        for attempt in range(2):
            content = self.chat(model, messages, schema=schema, **options)
            try:
                value = parse_json(content)
            except ModelOutputError:
                if attempt:
                    raise
                messages = [*messages, {"role": "assistant", "content": content},
                            {"role": "user", "content": "Answer with valid JSON only."}]
                continue
            if isinstance(value, dict):
                return value
            raise ModelOutputError("The model's JSON was not an object")
        raise ModelOutputError("The model did not answer with valid JSON")

    def _request(self, method: str, path: str, body: dict | None = None,
                 timeout: float | None = None) -> dict:
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(
            self.base_url + path, data=data, method=method,
            headers={"Content-Type": "application/json"} if data else {})
        try:
            with self._open(request, timeout=timeout or self.timeout) as response:
                return json.loads(response.read() or b"{}")
        except urllib.error.HTTPError as err:
            detail = _error_text(err)
            if err.code == 400 and "think" in detail:
                raise _ThinkUnsupported() from None
            if err.code == 404 and body and "model" in body:
                raise PipelineUnavailable(
                    f"The model {body['model']} is not installed on {self.name}") from None
            raise PipelineUnavailable(f"{self.name} answered HTTP {err.code}") from None
        except (OSError, ValueError, urllib.error.URLError):
            raise PipelineUnavailable(f"{_capital(self.name)} is not responding") \
                from None


class _ThinkUnsupported(Exception):
    pass


def _error_text(err: urllib.error.HTTPError) -> str:
    try:
        return err.read(4096).decode("utf-8", errors="replace").lower()
    except OSError:
        return ""


def _capital(text: str) -> str:
    return text[:1].upper() + text[1:]


@dataclass(frozen=True)
class SearchHit:
    url: str
    title: str
    snippet: str


class SearxClient:
    def __init__(self, base_url: str, *, timeout: float = 15,
                 opener=urllib.request.urlopen):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._open = opener

    def search(self, query: str, *, language: str | None = None) -> list[SearchHit]:
        params = {"q": query, "format": "json", "safesearch": "0"}
        if language:
            params["language"] = language
        url = f"{self.base_url}/search?{urlencode(params)}"
        try:
            with self._open(url, timeout=self.timeout) as response:
                reply = json.loads(response.read())
        except (OSError, ValueError, urllib.error.URLError):
            raise PipelineUnavailable("Web search (SearXNG) is not responding") from None
        hits = []
        for result in reply.get("results") or []:
            url = result.get("url") or ""
            if urlsplit(url).scheme in ("http", "https"):
                hits.append(SearchHit(url=url, title=result.get("title") or "",
                                      snippet=result.get("content") or ""))
        return hits


class Verifier:
    """The optional second checker: narrow yes/no questions to a different model.

    Research facts go to a claim-checking model (Bespoke-MiniCheck answers
    "Yes"/"No" to a document and a claim); review issues go to a general model
    of another family, so the second opinion is not the first model agreeing
    with itself.
    """

    def __init__(self, client: OllamaClient, research_model: str, review_model: str):
        self.client = client
        self.research_model = research_model
        self.review_model = review_model

    def up(self) -> bool:
        return self.client.available()

    def supports(self, claim: str, evidence: list[str]) -> bool:
        document = "\n".join(evidence)
        answer = self.client.chat(self.research_model, [
            {"role": "user", "content": f"Document: {document}\nClaim: {claim}"}],
            temperature=0)
        return _yes(answer)

    def confirms(self, issue: str, passage: str, reference: str | None) -> bool:
        context = f"Reference note:\n{reference}\n\n" if reference else ""
        answer = self.client.chat(self.review_model, [
            {"role": "system", "content": (
                "You double-check an editor's note on a passage of fiction. "
                "Answer only 'yes' if the note points at a real problem in the "
                "passage, or 'no' if it does not.")},
            {"role": "user", "content": (
                f"{context}Passage:\n{passage}\n\nEditor's note:\n{issue}\n\n"
                "Is the note right? Answer yes or no.")}],
            temperature=0)
        return _yes(answer)


def _yes(answer: str) -> bool:
    cleaned = _THINKING.sub("", answer or "").strip().lower()
    return cleaned.startswith("yes")
