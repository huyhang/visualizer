"""What the research and review pipelines share."""

from .models import OllamaClient, Verifier
from .pipelines import JobContext, PipelineUnavailable

_QUOTE_EDGES = " \t\n\"'“”‘’.…"


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
