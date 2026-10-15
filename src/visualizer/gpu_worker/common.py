"""What the research and review pipelines share."""

import os

from .models import OllamaClient, Verifier
from .pipelines import JobContext, PipelineUnavailable

_QUOTE_EDGES = " \t\n\"'“”‘’.…"
MAX_REPLACEMENT_CHARS = 1000


def second_check_mode(verify: str, verifier: Verifier | None) -> str:
    """run | skipped | caller_off | not_configured -- decided before any work."""
    if verify == "off":
        return "caller_off"
    if verifier is None:
        if verify == "required":
            raise PipelineUnavailable("No second checker is configured")
        return "not_configured"
    if not verifier.up():
        if verify == "required":
            raise PipelineUnavailable("The second checker is unreachable")
        return "skipped"
    return "run"


def ensure_loaded(ollama: OllamaClient, model: str, ctx: JobContext) -> None:
    if model not in ollama.loaded():
        ctx.progress("loading_model", "Loading the model")
        ollama.load(model)


def resolve_ref(value, known: set[str]) -> str | None:
    """The known ref the model meant, or None.

    Models echo references back decorated -- a kind prefix, brackets, the
    title tacked on -- so an exact match is tried first, then a known ref
    contained in what the model wrote, if exactly one is.
    """
    text = str(value or "").strip()
    if not text:
        return None
    if text in known:
        return text
    inside = [ref for ref in known if ref in text]
    return inside[0] if len(inside) == 1 else None


def clean_quote(value) -> str:
    """A model's quote without the ellipses and quote marks it wraps it in."""
    return str(value or "").strip(_QUOTE_EDGES).strip()


def clean_replacement(value, raw_quote, following: str = "",
                      limit: int = MAX_REPLACEMENT_CHARS) -> str | None:
    """The exact words to put in place of the quote ``clean_quote`` makes of
    ``raw_quote``, or None. ``following`` is the prose just after that quote.

    The replacement loses only what would not belong in the prose: the wrapping
    it shares with the raw quote, quote marks around the whole of it, and a stop
    the prose cannot take there. Its own punctuation is the fix, and stays. None
    when the model gave none, gave back the quote, ended on a stop that clashes
    with the prose's, or gave more than ``limit`` characters -- words cut short
    are no fix.
    """
    text = str(value or "").strip()
    raw = str(raw_quote or "").strip()
    quote = clean_quote(raw)
    start = raw.find(quote) if quote else 0
    text, left_out = _unshared(text, raw[:start], raw[start + len(quote):])
    # The prose itself says what follows; without it, what the quote left out.
    fitted = _fitted(_unwrapped(text), following or left_out)
    if not fitted or fitted == quote or len(fitted) > limit:
        return None
    return fitted


_WRAPS = {'"': '"', "“": "”", "'": "'", "‘": "’"}
_STOPS = ".!?…"


def _unshared(text: str, before: str, after: str) -> tuple[str, str]:
    """``text`` without the edges it shares with the wrapping ``clean_quote``
    took off the quote, and what of that wrapping's tail it did not share."""
    text = text[len(os.path.commonprefix([before, text])):]
    tail = len(os.path.commonprefix([after[::-1], text[::-1]]))
    return text[:len(text) - tail], after[:len(after) - tail]


def _unwrapped(text: str) -> str:
    """``text`` out of quote marks around the whole of it, with the stop inside
    or just after them: the model presenting its answer, not prose."""
    body = text[:-1] if text[-1:] in _STOPS else text
    if len(body) > 2 and _WRAPS.get(body[0]) == body[-1]:
        inner = body[1:-1]
        return (inner[:-1] if inner[-1:] in _STOPS else inner).strip()
    return text


def _fitted(text: str, after: str) -> str | None:
    """``text`` ending on a stop the prose ``after`` it can take, or None when
    the stop it ends on clashes with what follows."""
    stop = text[-1:]
    if not stop or stop not in _STOPS:
        return text
    next_char = after[:1]
    if next_char and next_char in _STOPS + ",;:":
        # Already there, or a full stop where the prose has a comma: drop it.
        if next_char == stop or (stop == "." and next_char in ",;:"):
            return text[:-1]
        return None
    if stop == "." and after.lstrip()[:1].islower():
        return text[:-1]  # a full stop cannot come before the sentence goes on
    return text
