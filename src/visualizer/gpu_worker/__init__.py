"""The AI worker that runs on the GPU box, serving the visualizer stack's jobs.

Akasha submits research jobs and Logos submits review jobs, over the v1 API in
``docs/gpu_worker/``; the worker runs them one at a time on the box's GPU and
keeps their results until they expire. It is the only thing that talks to
Ollama and SearXNG, which stay bound to the box's localhost.

Self-contained on purpose. It never imports the rest of ``visualizer`` --
``tests/gpu_worker/test_boundary.py`` checks, and ``docker/Dockerfile.worker``
copies nothing else into the image -- so it deploys to the box alone, and could
leave this repository without a rewrite.

Pipelines: ``research.py`` (plan, search, read, quote-check, write) and
``review.py`` (anchored issues against canon, research and deviations), on the
box's own models through ``models.py``, fetching only through ``fetch.py``.
"""
