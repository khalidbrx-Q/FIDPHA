# CLAUDE.md — WinInPharma Contributor Guide

@SKILL.md
@ARCHITECTURE.md

> Rules and decisions for anyone working on this codebase with Claude Code.
> Read top to bottom. Every rule is enforced.

---

## 1. Project at a Glance

Django 5.2 pharmacy loyalty platform. Three user-facing layers:

| Layer | URL prefix | Auth |
|---|---|---|
| Public API | `/api/v1/` | `Authorization: Token <raw>` (SHA-256 hashed server-side) |
| Pharmacy portal | `/portal/` | Session, allauth (Google), `is_staff=False` + `pharmacy_portal=True` |
| Control panel | `/control/` | Session, `is_staff=True` + Django permissions |

Apps: `fidpha` (core + portal), `sales` (ingestion), `api` (token-auth API), `control` (staff panel). Django admin disabled (URL commented out).

---

## 2. Business Logic — IMMUTABLE

> These rules are load-bearing. Do not change without a migration plan.

### 2.1 Points Formula

```
points = round(quantity × Sale.product_ppv × Contract_Product.points_per_unit)
```

One formula. Implemented in `_pts_qs()` in `fidpha/views.py` and `control/views.py`. Always filter `status=Sale.STATUS_ACCEPTED, product_ppv__isnull=False`.

### 2.2 The Three PPV Sources

| Field | Source | Use for points? |
|---|---|---|
| `Product.ppv` | Staff catalog | **NEVER** |
| `Sale.ppv` | Pharmacy submitted | **NEVER** |
| **`Sale.product_ppv`** | Snapshot at insert (frozen) | **ALWAYS** |

### 2.3 Hard Rules

- ✔ Use `Sale.product_ppv` for all points math.
- ✘ Never read `Product.ppv` or `Sale.ppv` for points.
- ✘ Never recompute points client-side.
- ✘ Never backfill `product_ppv` without a written migration plan.
- One **active** Contract per Account at most.
- `Sale.sale_datetime` must be **strictly after** `Contract.last_sale_datetime`.
- `Sale.sale_datetime.date() < today` (no same-day or future sales).
- API tokens stored as SHA-256 hashes. Plain token shown **once** at creation.
- Single ingestion entry point: `submit_sales_batch()` in `sales/services.py`.
- Auto-review requires **both** `SystemConfig.auto_review_enabled` AND `Account.auto_review_enabled`.

---

## 3. Architecture Rules

### 3.1 Layer Boundaries

| Layer | May depend on | Must NOT depend on |
|---|---|---|
| Models | ORM | views, services, HTTP |
| Services | models, transactions | views, request, JsonResponse |
| Views | services, models, request | other apps' internals |
| Templates | view context | direct ORM, business rules |

Services **never** import `django.http`, **never** receive `HttpRequest`.

### 3.2 API Design

Endpoints model **domain resources**, not screens.

- ✔ `/api/v1/contracts/{id}/sales/?month=2026-04`
- ✘ `/api/v1/dashboard-page-data/`

Filters via query params. Aggregations as sub-resources. Reuse the existing error envelope (`_error()` in `api/views.py`). Versioning in URL.

### 3.3 Two API Styles (do not mix)

| Namespace | Style | Auth |
|---|---|---|
| `/api/v1/` | Hand-rolled JSON, `_error()` envelope | Token |
| `/api/portal/` | DRF serializers, `PortalSessionPermission` | Session |
| `/api/staff/` | DRF serializers, `StaffSessionPermission` | Session |

---

## 4. Frontend vs Backend

**Backend owns:** business logic, validation, permissions, points math, authoritative data.

**Frontend owns:** presentation, formatting, UI state, client-side filter on small already-loaded datasets.

**Banned in frontend:** recomputing points, deriving status, re-checking permissions.

---

## 5. Branch Strategy

| Branch | Purpose |
|---|---|
| `main` | Production |
| `develop` | Active backend development |
| `feature/react-ui` | React SPA (paused — do not merge without approval) |
| `feature/improvements` | UI polish, SystemConfig enhancements, code-reviewer agent |
| `feature/postgres-migration` | PostgreSQL + Neon DB backend (not merged into develop yet) |
| `feature/production-hardening` | Phase 1 production infra: security headers, Gunicorn/WhiteNoise, JSON logging, /health/, Sentry, Redis (Upstash), Doppler — not merged into develop yet |
| `feature/deployment-automation` | Phase 2 in progress: Dockerfile + .dockerignore done (2.1). GitHub Actions CI + hosting + staging still pending. |
| `integration` | Long-running integration branch — safe merge zone for combining feature branches before they reach develop. Local-only deploys (no auto-deploy). |

- Never merge `feature/react-ui` into `develop` or `main` without explicit approval.
- Never modify portal templates for React convenience — they are the production fallback.

---

## 6. Coding Conventions

- Imports: stdlib → Django/3rd-party → local, blank-line separated.
- Named status constants — `Sale.STATUS_ACCEPTED/REJECTED/PENDING`, `Account/Contract/Product.STATUS_ACTIVE/STATUS_INACTIVE`. Never magic strings in queries.
- Models PascalCase singular; explicit `db_table`.
- Views snake_case with area prefix (`portal_dashboard`, `contracts_detail`).
- URL names snake_case; API routes kebab-case nouns.
- No comments unless the WHY is non-obvious.
- No docstrings on trivial functions.
- Match existing patterns in the file you edit.

---

## 7. Locked — Never Modify Without Approval

- Points formula and the three PPV fields.
- `Sale`, `SaleImport`, `Contract`, `Contract_Product` schemas.
- `/api/v1/contract/active/` and `/api/v1/sales/` request/response shapes.
- API token hashing (`api/authentication.py`, `APIToken.save()`).
- Auth flow (allauth config, adapters, OAuth).
- Already-applied migrations — no edits, no squashes.
- Disabled Django admin URL.

---

## 8. Quick Pointers

| Need | File |
|---|---|
| Points calc (portal) | `fidpha/views.py` `_pts_qs()` |
| Points calc (control) | `control/views.py` `_pts_qs()` |
| Sales ingestion | `sales/services.py` `submit_sales_batch()` |
| Active contract lookup | `fidpha/services.py` `get_active_contract()` |
| API token auth | `api/authentication.py` |
| Control decorators | `control/decorators.py` |
| Global config | `control/models.py` `SystemConfig.get()` |
| E2E tests | `tests-suite/e2e/` — 40 tests, 8 files (Tier 1 shipped 2026-05-24; 43 more planned in Tiers 2-4) |
| Unit tests | `tests-suite/unit/` — `test_api.py`, `test_fidpha.py`, `test_sales.py`, `test_control.py` (~196 tests, 1 skipped) |
| Code reviewer agent | `.claude/agents/code-reviewer.md` (outer `FIDPHA001/` folder) |
| Health endpoint | `FIDPHA001/health.py` → `GET /health/` (db + cache + migrations probes) |
| Sentry init | `FIDPHA001/settings.py` (env: `SENTRY_DSN`) |
| Cache/Redis config | `FIDPHA001/settings.py` `CACHES` dict (env: `REDIS_URL`) |
| Logging config | `FIDPHA001/settings.py` `LOGGING` dict; loggers under `wininpharma.*` |
| Gunicorn config | `gunicorn.conf.py` (workers, timeouts, logging) |
| Dockerfile | `Dockerfile` (multi-stage: builder + runtime, non-root `app` user, HEALTHCHECK on /health/) |
| Docker ignore list | `.dockerignore` (excludes secrets, .venv, frontend, db.sqlite3, etc.) |
| Docker Compose | `docker-compose.yml` (web service builds from Dockerfile + reads .env; optional commented postgres/redis for full offline mode) |
| CI/CD workflow | `.github/workflows/ci.yml` — 4 jobs: lint (ruff) + unit (pytest) + e2e (Playwright) + deploy (flyctl). Deploy only fires on push to `integration`. |
| Ruff config | `ruff.toml` (target py312, line 120, E402 ignored in setup-pattern scripts) |
| Dev/runtime split | `requirements.txt` (runtime only — what ships in Docker image) + `requirements-dev.txt` (pytest, ruff, playwright — CI/local only) |
| Fly.io config | `fly.toml` (app `fidpha-dev`, region `cdg`, auto-stop machines, release_command runs migrations) |
| Cloud dev URL | `https://fidpha-dev.fly.dev/` — Doppler `dev` config auto-syncs secrets to this app |

---

## 9. Common Commands

```bash
# Development
python manage.py runserver          # dev server (reads .env)
doppler run -- python manage.py runserver   # dev server (reads secrets from Doppler instead)
python manage.py migrate            # apply migrations
python manage.py makemigrations     # create new migration
python manage.py compilemessages    # compile French translations
python manage.py collectstatic      # collect static files (WhiteNoise compresses + hashes)

# Production server (Linux/container only — gunicorn doesn't run natively on Windows)
gunicorn FIDPHA001.wsgi:application -c gunicorn.conf.py

# Tests (live in tests-suite/ inside the repo)
pytest                              # all tests (pytest.ini points to tests-suite/)
pytest --ignore=tests-suite/e2e     # unit tests only
pytest tests-suite/e2e/             # e2e only (needs Playwright browsers)

# Observability
curl http://localhost:8000/health/  # health probe (db + cache + migrations)

# Docker (production-equivalent local runs)
docker build -t wininpharma:latest .                                  # build the image
docker run -p 8000:8000 --env-file .env --name wininpharma-dev wininpharma:latest    # run with .env
doppler run --mount secrets.env --mount-format docker -- \
    docker run -p 8000:8000 --env-file secrets.env --name wininpharma-dev wininpharma:latest    # run with Doppler secrets
docker ps                            # see (healthy)/(unhealthy) status
docker logs wininpharma-dev          # container logs
docker exec -it wininpharma-dev /bin/bash   # shell inside the container

# Docker Compose (preferred — shorter commands, same result)
docker compose up                    # build + start (foreground)
docker compose up -d                 # start detached
docker compose down                  # stop + remove
docker compose logs -f web           # tail web service logs
docker compose exec web bash         # shell in web container
docker compose ps                    # service-name-based status

# Linting (matches what CI runs)
ruff check .                         # zero warnings expected; CI fails on any
pip install -r requirements-dev.txt  # install ruff + pytest + playwright

# Fly.io (cloud dev environment — fidpha-dev.fly.dev)
fly status -a fidpha-dev             # machine state + last deploy
fly logs -a fidpha-dev               # tail live logs from cloud
fly ssh console -a fidpha-dev        # shell inside the running cloud machine
fly secrets list -a fidpha-dev       # secret names (values hidden; managed by Doppler sync)
fly deploy --remote-only             # manual deploy (CI does this automatically on push to integration)
```

## 10. CI/CD Pipeline

Push to ANY branch → CI runs (lint + unit + e2e). Push to `integration` → CI runs PLUS auto-deploy to fidpha-dev.

```
push (any branch)              push to integration            PR → develop / main
       │                              │                              │
       ▼                              ▼                              ▼
  CI: 3 test jobs            CI + deploy job              CI re-runs + REPO REVIEWER
   in parallel                                              (Claude routine)
       │                              │                              │
       ▼                              ▼                              ▼
   ✅ or ❌                  if green → flyctl deploy        PR mergeable if all
   (gates merge                  → fidpha-dev.fly.dev          checks + reviewer
    to develop/main)                                           give green
```

- **REPO REVIEWER** routines (Claude): 2 routines triggered on PR opened + synchronized for PRs targeting develop or main. Posts comment + email with severity-tagged findings. Filtered by author = khalidbrx-Q.
- **Branch protection** on `develop` and `main`: require 3 CI checks + up-to-date branch + no force pushes + no deletions. PR-required (0 approvals for solo dev).
- **Doppler-Fly sync**: changes to Doppler `dev` config auto-propagate to fidpha-dev Fly secrets within seconds; the affected machines auto-restart.

---
**End.** When in doubt: read the code, follow the existing pattern, ask before breaking a rule.
