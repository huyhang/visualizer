"""Run the worker without Docker: ``python -m visualizer.gpu_worker``.

For a laptop: point the dev server at it with ``GPU_WORKER_URL`` and
``GPU_WORKER_TOKEN`` to exercise the real HTTP path end to end. Binds to
localhost only; on the box, use the Docker image (``docker/gpubox/``).
"""

import argparse
import os

from werkzeug.serving import run_simple


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="python -m visualizer.gpu_worker")
    parser.add_argument("--port", type=int, default=8700)
    parser.add_argument("--db", default="instance/gpu_worker.sqlite3",
                        help="job store file (default: %(default)s)")
    args = parser.parse_args(argv)
    os.environ.setdefault("WORKER_DB", args.db)

    from .wsgi import application  # reads the environment, starts the runner

    run_simple("127.0.0.1", args.port, application, threaded=True)


if __name__ == "__main__":
    main()
