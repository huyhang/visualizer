# Combined image: every service behind one origin (single-port deployment).
#
# The four services share one MongoDB, one auth store and one secret, and always
# ship together, so this runs them in a single gunicorn via
# `visualizer.wsgi:application` (Werkzeug DispatcherMiddleware): akasha at `/`,
# chronos at `/timeline`, prithvi at `/prithvi`, logos at `/logos`. One published
# port -> one Synology reverse-proxy entry, one cookie, no CORS. (The
# per-service Dockerfiles still build each one standalone for development.)
#
# Build context is the repo root (see docker-compose.nas.yml).
FROM python:3.11-slim

WORKDIR /app

# Native text shaping for WeasyPrint, plus a metric-compatible serif: with no
# font package the image ships only DejaVu, so the print stylesheet's Times
# would silently resolve to a wider face and shift every line break.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies first so app-code edits don't invalidate this layer.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# The source tree is copied under /app/src so it imports as `visualizer.*`.
COPY src /app/src

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    MONGO_URI=mongodb://mongo:27017

EXPOSE 5000

# gthread workers handle idle browser keep-alive connections gracefully.
CMD ["gunicorn", "--bind", "0.0.0.0:5000", \
     "--workers", "2", "--worker-class", "gthread", "--threads", "4", \
     "--timeout", "60", "visualizer.wsgi:application"]
