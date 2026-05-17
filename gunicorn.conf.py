"""
Gunicorn production config for WinInPharma.

Run with:
    gunicorn FIDPHA001.wsgi:application -c gunicorn.conf.py

Most hosting platforms (Railway, Render, Heroku) auto-detect this file
when you start gunicorn — no extra flags needed.
"""

import multiprocessing
import os

# ---------------------------------------------------------------------------
# Network
# ---------------------------------------------------------------------------
# $PORT is injected by most hosting platforms; default to 8000 for local prod tests.
bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"

# ---------------------------------------------------------------------------
# Workers
# ---------------------------------------------------------------------------
# Industry-standard formula: (2 × CPU) + 1.
# WEB_CONCURRENCY env var lets the hosting platform override (Heroku, Railway, etc).
workers = int(os.environ.get("WEB_CONCURRENCY", multiprocessing.cpu_count() * 2 + 1))

# Sync workers — simple and reliable. Each worker handles one request at a time.
# For high concurrency / WebSockets, switch to "gevent" or "uvicorn.workers.UvicornWorker".
worker_class = "sync"

# Each worker has 4 threads — useful for I/O-bound work like DB queries.
threads = 4

# ---------------------------------------------------------------------------
# Timeouts
# ---------------------------------------------------------------------------
# Kill worker if a request takes longer than this (seconds). 30s is generous;
# anything slower is almost certainly a bug or runaway query.
timeout = 30

# Time given to in-flight requests when restarting workers.
graceful_timeout = 30

# Keep TCP connection alive between requests (faster repeated requests from same client).
keepalive = 5

# ---------------------------------------------------------------------------
# Worker recycling
# ---------------------------------------------------------------------------
# Restart each worker after this many requests. Defends against memory leaks
# in third-party packages (Django, Pillow, etc.).
max_requests = 1000

# Add randomness so workers don't all restart at once.
max_requests_jitter = 50

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
# Log to stdout/stderr — hosting platforms capture these automatically and
# ship them to their log aggregator (or Sentry / Better Stack later).
accesslog = "-"
errorlog = "-"
loglevel = os.environ.get("GUNICORN_LOG_LEVEL", "info")

# Access log format includes response time (%(L)s) — useful for spotting slow endpoints.
access_log_format = (
    '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s '
    '"%(f)s" "%(a)s" %(L)s'
)

# ---------------------------------------------------------------------------
# Process naming
# ---------------------------------------------------------------------------
proc_name = "wininpharma"
