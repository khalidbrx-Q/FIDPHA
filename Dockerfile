# syntax=docker/dockerfile:1.7
# =============================================================================
# WinInPharma — Production Dockerfile
# =============================================================================
# Multi-stage build:
#   STAGE 1 (builder) : heavy image with compilers, builds the virtualenv
#   STAGE 2 (runtime) : slim image with just the venv + app code — what deploys
#
# Build:   docker build -t wininpharma:latest .
# Run:     docker run -p 8000:8000 --env-file .env wininpharma:latest
# Health:  curl http://localhost:8000/health/
# =============================================================================


# =============================================================================
# STAGE 1 — BUILDER
# Compiles Python dependencies. Discarded after the build; only the resulting
# virtualenv is copied into the runtime stage.
# =============================================================================
FROM python:3.12-slim AS builder

# ─── Environment for the build ──────────────────────────────────────────────
# PYTHONDONTWRITEBYTECODE=1   : don't create __pycache__ (would be rebuilt anyway)
# PYTHONUNBUFFERED=1          : flush stdout/stderr immediately (so `docker logs` works)
# PIP_NO_CACHE_DIR=1          : don't keep pip's download cache (saves layer size)
# PIP_DISABLE_PIP_VERSION_CHECK=1 : skip the "new pip available" check
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# ─── System packages needed to COMPILE Python deps ──────────────────────────
# Some packages (psycopg2 from source, cryptography, etc.) need C compilers
# and dev headers. These are heavy (~300 MB) — that's why we discard this
# stage. The final runtime image will NOT have these.
#
# - build-essential : gcc, make, g++
# - libpq-dev       : PostgreSQL client headers (for psycopg2)
#
# Trick: && rm -rf /var/lib/apt/lists/* in the same RUN keeps the layer small
# (apt's package index can be 50+ MB if left behind).
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# ─── Create the virtualenv at a known location ──────────────────────────────
# Putting it in /opt/venv (instead of inside /app) makes it easy to copy as
# a single directory into the runtime stage.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# ─── Install Python deps — CACHE-FRIENDLY ORDER ─────────────────────────────
# We COPY only requirements.txt first, NOT the whole code.
#
# Docker caches each layer based on its inputs. If requirements.txt hasn't
# changed since the last build, Docker reuses the cached `pip install` layer
# (saves 30+ seconds). If we copied all code first, ANY code change would
# bust the cache and force a full reinstall.
WORKDIR /app
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install -r requirements.txt


# =============================================================================
# STAGE 2 — RUNTIME
# Slim image with only what's needed to RUN the app — no compilers, no
# dev headers. This is what gets pushed to your container registry and
# deployed to Railway / Render / wherever.
# =============================================================================
FROM python:3.12-slim AS runtime

# Same env hygiene as the builder, plus runtime-specific:
# - PATH includes the venv so `python` / `gunicorn` resolve to the venv's copies
# - DJANGO_SETTINGS_MODULE makes manage.py work without --settings flag
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    DJANGO_SETTINGS_MODULE=FIDPHA001.settings

# ─── Runtime-only system packages ──────────────────────────────────────────
# - libpq5 : PostgreSQL CLIENT LIBRARY (not the -dev headers — we don't compile here)
# - curl   : used by HEALTHCHECK below
# - gettext: required by `compilemessages` if you ever run i18n inside the container
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        curl \
        gettext \
    && rm -rf /var/lib/apt/lists/*

# ─── Non-root user — security best practice ────────────────────────────────
# Containers should NEVER run as root. If an attacker exploits a Django bug,
# they shouldn't get root inside the container. Creating a dedicated 'app'
# user limits the blast radius.
RUN useradd --create-home --shell /bin/bash --uid 1000 app

# ─── Bring the prebuilt virtualenv from the builder stage ──────────────────
# --from=builder means "copy from the named stage above, not from the host"
# --chown=app:app gives the new user ownership (so it can read/execute the venv)
COPY --from=builder --chown=app:app /opt/venv /opt/venv

# ─── App working directory ──────────────────────────────────────────────────
# /app is conventional. WORKDIR creates the dir if needed, and `cd`s into it.
# IMPORTANT: WORKDIR runs as root here (USER comes after), so /app is created
# root-owned. We chown it to `app` so the non-root user can write files in it
# (e.g. log files, user uploads, anything else). Without this, the app user
# can read /app's contents but can't create new files there.
WORKDIR /app
RUN chown app:app /app

# Switch to the non-root user for everything that follows.
USER app

# ─── Copy the application code ──────────────────────────────────────────────
# LAST among the major COPY steps. Why? Because code changes constantly,
# and putting this near the bottom means earlier layers (deps, system packages)
# stay cached even when you edit Python files.
COPY --chown=app:app . .

# ─── Pre-build static files into the image ─────────────────────────────────
# `collectstatic` gathers CSS/JS/images from all apps into STATIC_ROOT.
# Doing it here (build time) instead of at startup means:
#   - Faster container starts
#   - Static files are baked in; no runtime surprises
#
# We set dummy values for vars that settings.py reads at import time.
# These don't affect the static files themselves — they're just to let
# Django boot enough to run the command.
RUN SECRET_KEY=build-time-dummy \
    DEBUG=False \
    ALLOWED_HOSTS=localhost \
    python manage.py collectstatic --noinput

# ─── Document the port (informational only) ────────────────────────────────
# EXPOSE does NOT actually open a port — you still need `-p 8000:8000` at
# `docker run` time. It's a hint for tools and other developers.
EXPOSE 8000

# ─── Health probe — orchestrators read this ────────────────────────────────
# Docker / Railway / Kubernetes hit /health/ every 30 seconds.
# If 3 in a row fail, the container is marked "unhealthy" and gets restarted.
# Our /health/ endpoint already checks db + cache + migrations.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl --fail http://localhost:8000/health/ || exit 1

# ─── The command to run when the container starts ──────────────────────────
# Uses gunicorn.conf.py (workers, timeouts, logging — set up in Phase 1.2).
# JSON-array form (vs shell form) means signals (like SIGTERM) reach gunicorn
# directly instead of going through a /bin/sh wrapper — important for graceful
# shutdown.
CMD ["gunicorn", "FIDPHA001.wsgi:application", "-c", "gunicorn.conf.py"]
