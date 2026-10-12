"""Combined production entrypoint: every service on one port/origin.

akasha at ``/``, chronos at ``/timeline``, prithvi at ``/prithvi``, logos at
``/logos``, wired by ``visualizer.stack.build_application`` over a real
MongoDB. Run with ``gunicorn visualizer.wsgi:application``.

The same wiring runs without Docker or MongoDB as ``python -m
visualizer.devserver``. The per-service entrypoints (``visualizer.akasha.wsgi``
and its siblings) still exist for running one service standalone.
"""

from visualizer.akasha.config import get_mongo_client
from visualizer.stack import build_application

application = build_application(get_mongo_client())
