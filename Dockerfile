# Pinned to the previous stable Debian release deliberately. The newest release renamed a large
# set of library packages (a "t64" suffix) and removed others, which breaks most published
# OpenCV/imaging recipes. Pinning removes a whole class of build failure.
FROM python:3.13-slim-bookworm AS base

# opencv-python-headless is used rather than opencv-python: it drops the libGL runtime dependency
# entirely, so the image needs only the glib runtime.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=0 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# NOTE: no ARG for any secret. The hosting platform passes a service's environment variables into
# the build automatically, so a matching ARG would bake the value into an image layer.
COPY pyproject.toml README.md ./
COPY pidgraph ./pidgraph
RUN pip install --no-cache-dir -e .

COPY docs ./docs
COPY supabase ./supabase

# Storage is exercised the same way here as in production: the hosted filesystem is ephemeral, so
# anything written to local disk is lost on restart.
ENV PIDGRAPH_STORAGE_BACKEND=supabase \
    PIDGRAPH_INPUT_DIR=/app/data

ENTRYPOINT ["python", "-m", "pidgraph.cli"]
CMD ["doctor"]
