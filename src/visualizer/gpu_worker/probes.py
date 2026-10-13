"""The worker's view of the box: what ``GET /v1/health`` reports.

Each probe is short and local -- Ollama and SearXNG on localhost, ``nvidia-smi``
for memory -- so health answers inside the stack's 2-second budget even when a
dependency is down. A probe that cannot get an answer reports ``down`` (or, for
the GPU, unknown figures); it never raises.
"""

import json
import subprocess
import urllib.error
import urllib.request

from .config import WorkerConfig

# Memory held by something other than Ollama, above this share of the card,
# means another workload (ComfyUI, usually) has the GPU.
BUSY_SHARE = 0.5


def gpu_section(used_mb: int | None, total_mb: int | None,
                ollama_mb: int) -> dict:
    """``gpu`` for health: busy when another process holds most of the memory."""
    busy = (used_mb is not None and total_mb is not None
            and used_mb - ollama_mb > total_mb * BUSY_SHARE)
    return {"busy": busy, "vram_used_mb": used_mb, "vram_total_mb": total_mb}


def parse_nvidia_smi(output: str) -> tuple[int | None, int | None]:
    """(used, total) MiB from ``--query-gpu=memory.used,memory.total``, first GPU."""
    try:
        used, total = (int(part.strip()) for part in output.splitlines()[0].split(","))
    except (IndexError, ValueError):
        return None, None
    return used, total


class SystemProbes:
    def __init__(self, config: WorkerConfig, *, run=subprocess.run,
                 opener=urllib.request.urlopen):
        self.config = config
        self._run = run
        self._open = opener

    def snapshot(self) -> dict:
        """The four health sections the worker reports about its surroundings."""
        loaded, ollama_mb, ollama_up = self._ollama_ps()
        used, total = self._nvidia_smi()
        return {
            "ollama": {"status": "up" if ollama_up else "down",
                       "models": {"review": self.config.review_model,
                                  "research": self.config.research_model},
                       "loaded": loaded},
            "searxng": {"status": "up" if self._answers(
                f"{self.config.searxng_url}/healthz") else "down"},
            "gpu": gpu_section(used, total, ollama_mb),
            "verifier": self._verifier(),
        }

    def _ollama_ps(self) -> tuple[list[str], int, bool]:
        """Models in VRAM, the MiB they hold, and whether Ollama answered at all."""
        reply = self._get_json(f"{self.config.ollama_url}/api/ps")
        if reply is None:
            return [], 0, False
        models = (reply.get("models") if isinstance(reply, dict) else None) or []
        models = [m for m in models if isinstance(m, dict)]
        names = [m.get("name") or m.get("model") for m in models]
        vram = sum(int(m.get("size_vram") or 0) for m in models) // (1024 * 1024)
        return [n for n in names if n], vram, True

    def _nvidia_smi(self) -> tuple[int | None, int | None]:
        try:
            completed = self._run(
                ["nvidia-smi", "--query-gpu=memory.used,memory.total",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=self.config.probe_timeout,
                check=False)
        except (OSError, subprocess.SubprocessError):
            return None, None
        if completed.returncode != 0:
            return None, None
        return parse_nvidia_smi(completed.stdout)

    def _verifier(self) -> dict:
        if not self.config.verifier_url:
            return {"status": "not_configured",
                    "models": {"research": None, "review": None}}
        up = self._get_json(f"{self.config.verifier_url}/api/tags") is not None
        return {"status": "up" if up else "down",
                "models": {"research": self.config.verifier_research_model,
                           "review": self.config.verifier_review_model}}

    # -- HTTP ----------------------------------------------------------------

    def _get_json(self, url: str):
        try:
            with self._open(url, timeout=self.config.probe_timeout) as response:
                return json.loads(response.read(1024 * 1024))
        except (OSError, ValueError, urllib.error.URLError):
            return None

    def _answers(self, url: str) -> bool:
        """Up if anything answers below 500 -- even a 404 means the server runs."""
        try:
            with self._open(url, timeout=self.config.probe_timeout):
                return True
        except urllib.error.HTTPError as err:
            return err.code < 500
        except (OSError, urllib.error.URLError):
            return False
