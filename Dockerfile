# Pinned to the previous stable Debian release deliberately. The newest release renamed a large
# set of library packages (a "t64" suffix) and removed others. Pinning removes a whole class of
# build failure.
FROM python:3.13-slim-bookworm AS base

# tesseract ships in the image because recognition is part of the pipeline: without it every
# cache miss silently degrades to an unread label, which in a container looks like a drawing
# with less text on it.
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=0 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# NOTE: no ARG for any secret. A matching build-arg bakes the value into an image layer.
COPY pyproject.toml README.md ./
COPY pidgraph ./pidgraph
RUN pip install --no-cache-dir -e .

COPY docs ./docs
COPY supabase ./supabase
# The committed recognition cache. Without it a container re-runs the engine on every crop the
# repository has already answered.
COPY codebook ./codebook

# Compose mounts ./outputs. Optional Supabase persist is selected at runtime when DATABASE_URL is set.
ENV PIDGRAPH_INPUT_DIR=/app/data

ENTRYPOINT ["python", "-m", "pidgraph.cli"]
CMD ["doctor"]
