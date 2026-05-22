# ARCHITECTURE.md — FIDPHA001 Reference

> Deep reference for the FIDPHA001 / WinInPharma platform. Read this for **orientation**, schema, route maps, and migration history.
> **Rules and decisions live in [CLAUDE.md](CLAUDE.md), not here.** When this file and CLAUDE.md disagree, CLAUDE.md wins.

---

## 1. System Purpose

Django pharmacy loyalty platform (PFE internship). Pharmacies push their daily sales via a token-authenticated API. Each accepted sale earns the pharmacy points, computed from a per-product multiplier inside an active contract. Pharmacies log into a portal to see their points, contracts, and sales history. Staff manage everything from a custom control panel that replaces Django admin.

---

## 2. Stack

Verified from `FIDPHA001/settings.py`:

- **Django 5.2** · **Python 3.x** · **Three-way DB backend** toggled by `DB_BACKEND` in `.env`: `sqlite` (default, local `db.sqlite3`), `local` (PostgreSQL on localhost, `wininpharma_db`), `neon` (Neon cloud PostgreSQL, AWS eu-west-2 London). `psycopg2-binary` required for PostgreSQL backends.
- **WSGI server**: **Gunicorn** (`gunicorn.conf.py` — workers=(2×CPU)+1, sync class, 30s timeout, max-requests=1000+jitter, stdout logging). `runserver` still works locally for dev.
- **Static files**: **WhiteNoise** middleware right after `SecurityMiddleware`. `CompressedManifestStaticFilesStorage` — compressed (gzip/brotli) + hashed filenames for unbreakable caching. In `DEBUG=True` mode it transparently lets `runserver` serve statics.
- **Cache & sessions**: Redis (Upstash) when `REDIS_URL` is set — `django_redis.cache.RedisCache` + `cached_db` sessions (Redis-fast reads, DB-durable writes). Falls back to `LocMemCache` + DB sessions when `REDIS_URL` is empty.
- **Error tracking**: **Sentry** (`sentry-sdk[django]`) initialized in `settings.py` when `SENTRY_DSN` is set. Auto-captures all unhandled exceptions via `DjangoIntegration`. `traces_sample_rate=1.0` in DEBUG, `0.1` in production. `send_default_pii=False` (GDPR-safe).
- **Logging**: structured via `python-json-logger`. `LOGGING` dict in `settings.py`. Two formatters — `verbose` (human-readable, DEBUG mode) and `json` (production). Loggers under `wininpharma.*` namespace (e.g. `wininpharma.health`, `wininpharma.api`).
- **Secrets management**: dual-mode. **Doppler** (cloud, project `fidpha`, config `dev`) via `doppler run -- <cmd>` — secrets injected as env vars. Falls back to local `.env` (gitignored) when Doppler isn't used. `python-decouple` reads from env first, then `.env`.
- **Containerization** (on `feature/deployment-automation`): multi-stage `Dockerfile` at the repo root. Stage 1 (builder) = `python:3.12-slim` + build-essential + libpq-dev, builds `/opt/venv` with all pip deps. Stage 2 (runtime) = `python:3.12-slim` + libpq5 + curl + gettext, copies the venv from builder, runs as non-root `app` user (uid 1000), `collectstatic` at build time, `EXPOSE 8000`, `HEALTHCHECK` against `/health/` every 30s, `CMD` = `gunicorn FIDPHA001.wsgi:application -c gunicorn.conf.py`. Final image ~150 MB. `.dockerignore` excludes secrets/`.venv`/`frontend/`/`db.sqlite3`/`.git`/etc. Tested locally with `--env-file .env` and Neon + Upstash + Sentry — full cloud-services stack from a local Linux container.
- **`docker-compose.yml`** (local dev only): declarative wrapper around `docker run`. Defines the `web` service (builds from Dockerfile + maps port 8000 + reads .env + restart=unless-stopped). Includes commented-out `postgres:16-alpine` + `redis:7-alpine` services with named volumes + healthchecks for full offline mode (uncomment and switch `.env` to `DB_BACKEND=local`, `LOCAL_DB_HOST=postgres`, `REDIS_URL=redis://redis:6379`). Production hosting (Railway/Render) reads the Dockerfile directly — compose is NOT used in production.
- **DRF** — partially adopted: `APIView`, `Response`, `BaseAuthentication`, `BasePermission`, throttling, `URLPathVersioning`, serializers (used in `/api/portal/` and `/api/staff/` only). No viewsets, routers, or browsable API in production.
- **django-allauth** — Google OAuth active; Apple planned (deferred).
- **django-unfold** — themes Django admin (admin still registered for fallback; URL is commented out).
- **Frontend (Django)**: vanilla JS + ECharts via CDN (SVG renderer), Material Icons Round, Inter font, no build step.
- **CSS**: single `fidpha/static/fidpha/css/portal.css` shared by portal AND control.
- **React SPA** (`feature/react-ui` branch): Vite 6 + React 18 + react-router-dom v7. Lives at `FIDPHA001/FIDPHA001/frontend/`. Design system: **shadcn/ui + Tailwind CSS** (planned). Charts: `echarts-for-react` (requires `tslib` peer dep). Auth: session cookie + CSRF. Talks to `/api/portal/` and `/api/staff/` endpoints. In dev, Vite proxies all Django paths to `localhost:8000`. In production, Django serves the built `index.html` at `/app/` and `/control-app/`.
- **Email**: Gmail SMTP, sender `WinInPharma <buarramoukhalid@gmail.com>`. Verification and password reset emails use `EmailMultiAlternatives` (HTML + text). HTML templates in `fidpha/templates/fidpha/email/` and `templates/registration/`.
- **i18n**: `USE_I18N=True`, `LocaleMiddleware` active, `LANGUAGES=[('fr','French'),('en','English')]`. Translations at `locale/fr/LC_MESSAGES/django.po/.mo`. GNU gettext required to compile (`C:\Program Files\gettext-iconv\bin`).
- **Time zone**: `Africa/Casablanca`, `USE_TZ=True`. API treats naive incoming datetimes as UTC.

---

## 3. Repo Layout

```
FIDPHA/                              ← repo root (git root) — manage.py is here
├── CLAUDE.md
├── ARCHITECTURE.md                  ← this file
├── manage.py
├── db.sqlite3
├── requirements.txt
├── FIDPHA001/                       ← Django project package
│   ├── settings.py
│   ├── urls.py
│   ├── test_runner.py
│   └── asgi.py / wsgi.py
├── fidpha/                          ← core: models, portal views, services, allauth adapters
├── api/                             ← REST API layer (token auth v1 + session auth portal/staff)
├── sales/                           ← ingestion + Sale/SaleImport models
├── control/                         ← staff control panel (CRUD + sales review + sync log)
├── templates/registration/          ← password reset (project-level)
├── templates/react/                 ← index.html + staff_index.html (SPA shells, served by Django)
├── locale/fr/LC_MESSAGES/           ← French translations (.po source + .mo compiled)
├── static/                          ← admin.css, admin/*.js (django-unfold enhancements)
└── frontend/                        ← React SPA (Vite 6 + React 18), feature/react-ui only
    ├── src/
    │   ├── api/client.js            ← fetch wrapper (session + CSRF)
    │   ├── components/Layout.jsx
    │   └── pages/Dashboard.jsx, Contracts.jsx, Points.jsx, Pharmacy.jsx
    ├── vite.config.js               ← proxy to Django localhost:8000 in dev
    └── package.json
```

---

## 4. Apps

### 4.1 `fidpha` — core domain

- `models.py` — `Account`, `UserProfile`, `Product`, `Contract`, `Contract_Product`, `RoleProfile`, `TraceableMixin`.
- `views.py` — portal views: `custom_login`, `portal_dashboard`, `portal_contracts`, `portal_sales`, `portal_pharmacy`, `portal_profile`, `setup_profile`, `verify_pending`, `verify_email`, `CustomPasswordResetView`/`...Confirm`.
- `services.py` — `get_account`, `get_active_contract`, `get_contract_products`, `get_available_products_for_contract`, `get_active_contracts_for_product`, `link_product_to_contract`, `bulk_import_products(rows, created_by)` (returns `{created, skipped}`), `bulk_link_products_to_contract(contract, rows, created_by)` (returns `{created, skipped}`; skips inactive products when contract is active). Custom exceptions: `AccountNotFoundError`, `ContractNotFoundError`, `ProductNotFoundError`, `ProductAlreadyLinkedError`.
- `adapters.py` — `FIDPHASocialAccountAdapter` (Google OAuth), `FIDPHAAccountAdapter` (suppresses default allauth messages).
- `admin.py` — Django admin registrations using `unfold.admin.ModelAdmin`. Admin URL is **not routed** (commented out in `FIDPHA001/urls.py`); this file is dormant unless the URL is re-enabled.
- `admin_api.py` — three legacy AJAX endpoints used by Django admin pages, still wired in root `urls.py`: `available_products_api`, `add_contract_product_api`, `product_toggle_api`.
- `utils.py` — admin sidebar badge callables referenced from `UNFOLD['SIDEBAR']` in settings.
- `urls.py` — `/portal/*` routes (`app_name="fidpha"`).
- `templates/fidpha/`, `static/fidpha/` (`css/portal.css`, `css/login.css`, `js/portal.js`).
- `legacy_models.py` — **legacy / inactive**, do not edit/import.

### 4.2 `api` — REST API layer

**Token-auth v1 (pharmacy machines):**
- `models.py` — `APIToken`, `APITokenUsageLog`.
- `authentication.py` — `APITokenAuthentication`. Hashes `Authorization: Token <raw>` with SHA-256, looks up by hash, bumps usage, writes `APITokenUsageLog`.
- `permissions.py` — `HasAPIToken` (DRF `BasePermission`). `PortalSessionPermission` and `StaffSessionPermission` (session-auth gates for React endpoints).
- `throttles.py` — `APITokenThrottle(SimpleRateThrottle)`. Scope `api_token`. Rate is dynamic: reads `SystemConfig.api_token_rate_limit` via Django cache (TTL 60 s); 0 = unlimited. Cache key = `token.pk`. Falls through to `AnonRateThrottle` if no token.
- `views.py` — `ActiveContractView` (GET `/api/v1/contract/active/`), `SalesSubmitView` (POST `/api/v1/sales/`), `custom_exception_handler` (uniform error envelope).
- `urls.py` — two routes (`active_contract`, `sales_submit`).

**Session-auth portal API (React pharmacy portal):**
- `portal_views.py` — 10 view classes: `PortalAccountView`, `DashboardStatsView`, `DashboardChartsView`, `DashboardRecentSalesView`, `PortalContractsListView`, `PortalActiveContractView`, `ContractChartsView`, `PortalSalesStatsView`, `PortalSalesListView`, `SalesChartsView`. All use `SessionAuthentication + PortalSessionPermission`, `throttle_classes = []`.
- `portal_urls.py` — 10 routes under `/api/portal/`.

**Session-auth staff API (React control panel — future):**
- `staff_views.py` — full CRUD + review + stats views. `SessionAuthentication + StaffSessionPermission`.
- `staff_urls.py` — 26 routes under `/api/staff/`.

**Shared:**
- `serializers.py` — DRF serializers used by portal and staff views (not used by v1 views).

### 4.3 `sales` — ingestion + storage

- `models.py` — `SaleImport` (raw, indexed `batch_id` and `(account_code, status)`), `Sale` (validated, 1-1 PROTECT to SaleImport).
- `services.py` — `submit_sales_batch(account_code, batch_id, sales_data, token)` — single ingestion entry point. `BatchTooLargeError` when batch exceeds `SystemConfig.max_batch_size` (read via Django cache, TTL 30 s; 0 = unlimited). Idempotency via `_response_from_existing_batch()`.
- `views.py` — empty stub (no Django HTTP views; everything goes through `api/views.py`).

### 4.4 `control` — staff control panel

- `models.py` — `SystemConfig` (single-row table, `get_or_create(pk=1)`): `auto_review_enabled` bool, `auto_review_updated_by` FK, `auto_review_updated_at`. Also: `max_batch_size`, `ppv_tolerance_percent`, `rejection_rate_warn_threshold`, `rejection_rate_danger_threshold`, `api_token_rate_limit` (all with 0/None = disabled sentinel; see model section).
- `views.py` — `dashboard`, full CRUD for roles/users/accounts/contracts/products/tokens, sales review (batch list + accept/reject + bulk + export), social-app/social-account/site config, sync_log, `system_settings`.
- `forms.py` — `AccountForm`, `ContractForm`, `ContractProductForm` (+ `ContractProductFormSet` with extended `BaseInlineFormSet` supporting "delete and re-add same product"), `RoleForm`, `UserForm`, `ProductForm`, `TokenForm`, `SocialAppForm`, `SiteForm`.
- `decorators.py` — `staff_required`, `perm_required`, `superuser_required`.
- `urls.py` — `/control/*` routes (`app_name="control"`).
- `templates/control/` (no per-app static; reuses `portal.css`).

---

## 5. Models — Field Inventory

### `Account` (`db_table="Account"`)
- `code` (unique CharField), `name`, `city`, `location` (TextField), `phone`, `email`, `pharmacy_portal` (bool — gates portal login), `status` ∈ {active, inactive}.
- `auto_review_enabled` (bool, default False) — per-account opt-in for auto-review. Only takes effect when `SystemConfig.auto_review_enabled` is also True.
- Inherits `TraceableMixin`.
- `clean()`: blocks deactivation if any active contract exists.

### `UserProfile` (`db_table="UserProfile"`)
- 1-1 to `auth.User` (related_name="profile").
- FK to `Account` (related_name="users").
- `email_verified` (bool), `verification_token`, `token_created_at` (24h expiry on the verification flow).

### `Product` (`db_table="Product"`)
- `code` (unique), `designation`, **`ppv`** (DecimalField 10,2, **nullable**), `status` ∈ {active, inactive}.
- `clean()`: blocks deactivation if referenced by any active contract.

### `Contract` (`db_table="Contract"`)
- `title`, `designation` (TextField), `start_date`, `end_date` — both **DateTimeField**, not DateField.
- FK `account` (related_name="contracts").
- M2M `products` through `Contract_Product`.
- `status` ∈ {active, inactive}.
- Sync state: `last_sync_at`, `last_sale_datetime` — updated atomically by `submit_sales_batch`.
- `.duration` property — capped at 2 units (years/months/days).
- `clean()`: start ≤ end; only one active contract per account; cannot activate while any linked product is inactive. Reads `_pending_cp_deletes` (set by `contracts_edit` view) to exclude CP rows that are being deleted in the same form submission — without this, the inactive-product check sees stale DB state before `formset.save()` runs.

### `Contract_Product` (`db_table="Contract_Product"`, junction)
- FKs `contract`, `product`.
- `external_designation` — pharmacy's internal name for this product.
- **`points_per_unit`** — DecimalField(6,2), default 1.
- `target_quantity` (PositiveIntegerField, nullable).
- `unique_together = [("contract","product"), ("contract","external_designation")]`.
- `clean()` surfaces the unique-together as a friendly error; supports `_skip_unique_pks` for delete-and-re-add formset submissions.

### `RoleProfile` (`db_table="RoleProfile"`)
- 1-1 to `auth.Group`. Single field: `icon` (Material Icon name; default `'badge'`).

### `SaleImport` (`db_table="SaleImport"`, raw staging)
- `batch_id`, `account_code`, `external_designation`, `sale_datetime`, `creation_datetime`, `quantity`, `ppv` (Decimal 10,2 — pharmacy-submitted).
- `contract_product` (nullable FK, resolved at validation).
- `status` ∈ {pending, accepted, rejected}, `rejection_reason`.
- `received_at` (auto_now_add), `token` (FK→APIToken, SET_NULL).
- `inserted_by`, `reviewed_by`, `reviewed_at`.
- Indexes: `batch_id`; `(account_code, status)`.

### `Sale` (`db_table="Sale"`, validated, points-bearing)
- `sale_import` (1-1 PROTECT — every Sale traceable to its raw row).
- `contract_product` (FK PROTECT).
- `sale_datetime`, `creation_datetime`, `quantity`, `ppv` (pharmacy-submitted), **`product_ppv`** (snapshot of `Product.ppv` at insert; nullable for legacy).
- `status` ∈ {pending, accepted, rejected} — staff review status; defaults to pending (added in `sales/0003`).
- `rejection_reason` (CharField 500, blank, default="" — reviewer-entered reason on manual reject; migration `sales/0007`).
- `auto_reviewed` (bool, default False — True when accepted by the auto-review system, not a staff user; `reviewed_by` stays None; migration `sales/0008`).
- `reviewed_by`, `reviewed_at`, `created_at`, `token`, `inserted_by`.
- Index: `(contract_product, sale_datetime)`.

### `APIToken`
- `name`, `token` (SHA-256 hex 64-char unique), `token_suffix` (last 4 chars of raw, display).
- `is_active`, `created_at`, `created_by`, `last_used_at`, `usage_count`, `masked_token` property.
- `save()`: if `token` empty, generates `secrets.token_hex(32)`, stashes raw on `self.raw_token` (transient — readable **once** in same Python instance), stores SHA-256.

### `SystemConfig` (`db_table="SystemConfig"`, single-row)
- Accessed via `SystemConfig.get()` (`get_or_create(pk=1)`).
- `auto_review_enabled` (bool, default False) — global kill-switch; per-account `Account.auto_review_enabled` is the secondary gate.
- `auto_review_updated_by` (FK→User, SET_NULL, nullable), `auto_review_updated_at` (auto_now).
- `max_batch_size` (PositiveIntegerField, default 0) — max rows per API batch; 0 = unlimited. Used by `sales/services.py` (cached 30 s).
- `ppv_tolerance_percent` (DecimalField 5,2, nullable) — reject rows where submitted PPV deviates more than this % from catalog PPV. None/blank = disabled. Stored but enforcement in ingestion is future work.
- `rejection_rate_warn_threshold` (PositiveSmallIntegerField, default 0) — batch rejection rate % above which a yellow badge shows in sales review. 0 = disabled.
- `rejection_rate_danger_threshold` (PositiveSmallIntegerField, default 0) — batch rejection rate % above which a red badge shows. Must exceed warn threshold. 0 = disabled.
- `api_token_rate_limit` (PositiveIntegerField, default 0) — max API requests per token per hour; 0 = unlimited. Read by `api/throttles.py` (cached 60 s).
- `clean()` validates all constraints (ranges, warn < danger). View calls `full_clean()` before save.
- Settings page: `/control/settings/system/` (superuser only) — 4 card sections: Auto-Review, Sales Ingestion, Review Thresholds, API Throttling.

### `APITokenUsageLog`
- `token` (FK), `called_at` (db_index, default now), `endpoint` (str). Created on every authenticated API call.

### `TraceableMixin` (abstract)
- `created_by`, `created_at` (auto_now_add), `modified_by`, `modified_at` (auto_now). Set `created_by`/`modified_by` in views before save.

---

## 6. URL Map

### 6.1 Root (`FIDPHA001/urls.py`)

| URL | Target |
|---|---|
| `/` | redirect → `/portal/login/` |
| `/health/` | `FIDPHA001.health.health` — unauthenticated; returns `{db, cache, migrations}` status (200 ok / 503 degraded) |
| `/admin/login/` | redirect → `/portal/login/` |
| `/admin/logout/` | `fidpha_views.custom_logout` |
| `/admin/welcome/` | `fidpha_views.admin_welcome` (OAuth post-login flash) |
| `/admin/` | **commented out** — admin not routed |
| `/api/contract/<int>/available-products/` | `available_products_api` (legacy admin AJAX) |
| `/api/contract/<int>/add-product/` | `add_contract_product_api` (legacy admin AJAX) |
| `/api/product/<int>/toggle/` | `product_toggle_api` (legacy admin AJAX) |
| `/accounts/password_reset/` | `CustomPasswordResetView` |
| `/accounts/reset/<uidb64>/<token>/` | `CustomPasswordResetConfirmView` |
| `/accounts/` | `django.contrib.auth.urls` (include) |
| `/portal/` | `fidpha.urls` |
| `/auth/` | `allauth.urls` |
| `/api/v1/` | `api.urls` (token auth) |
| `/api/portal/` | `api.portal_urls` (session auth — React pharmacy portal) |
| `/api/staff/` | `api.staff_urls` (session auth — React control panel) |
| `/app/` and `/app/<path>/` | `spa_view` → serves `templates/react/index.html` |
| `/control-app/` and `/control-app/<path>/` | `staff_spa_view` → serves `templates/react/staff_index.html` |
| `/control/` | `control.urls` |

### 6.2 Portal (`fidpha/urls.py`, `app_name="fidpha"`)

| Path | View |
|---|---|
| `login/` | `custom_login` (staff → /control/, portal → /portal/dashboard/) |
| `logout/` | `custom_logout` |
| `dashboard/` | `portal_dashboard` (4 stat cards + 4 charts) |
| `pharmacy/` | `portal_pharmacy` (account info + edit profile + change password) |
| `contracts/` | `portal_contracts` (active contract products + monthly trend with cross-chart drill-down) |
| `sales/` | `portal_sales` ("Points Breakdown" — sales table + searchable contract dropdown + acceptance rate pill + status charts + year selector) |
| `setup-profile/` | `setup_profile` |
| `verify-pending/` | `verify_pending` (resends email) |
| `verify-email/<token>/` | `verify_email` (24h expiry) |
| `profile/` | `portal_profile` |
| `profile/password/` | `portal_profile_password` |

### 6.3 Public API (`api/urls.py`)

| Path | View | Method |
|---|---|---|
| `/api/v1/contract/active/?account_code=PH-XXX` | `ActiveContractView` | GET |
| `/api/v1/sales/` | `SalesSubmitView` | POST |

Request/response shapes documented in docstrings on each view.

### 6.4 Control (`control/urls.py`, `app_name="control"`)

- `/control/` — dashboard (stats + 25 most recent LogEntry rows).
- `/control/roles/` (CRUD) — Django Groups + RoleProfile.
- `/control/users/` (CRUD) — three user types: superuser/staff/portal.
- `/control/accounts/` (CRUD).
- `/control/contracts/` (CRUD; detail has trend + Points-by-Product cross-chart):
  - `/control/contracts/<pk>/import-products/` — server-side bulk-link endpoint (exists in URL map; no longer called from frontend — import modal now uses client-side formset path exclusively).
  - `/control/contracts/<pk>/unlink-product/<cp_pk>/` (POST) — `contracts_unlink_product`; AJAX immediate delete of a `Contract_Product` row. Returns `{"ok": true}`. Used by the contract edit form's unlink button to persist unlinking without a full form save.
- `/control/products/` (CRUD) + `/control/products/import/` (POST JSON → bulk create via `bulk_import_products()` service).
- `/control/tokens/` (CRUD + revoke + reactivate; detail has 30-day usage chart).
- `/control/sales/` — sales review (batch list with inline expansion, accept/reject, bulk update, CSV export):
  - `/control/sales/api/contracts/?account=` (JSON)
  - `/control/sales/api/batches/?contract=` (JSON)
  - `/control/sales/api/batches-v2/` (paginated batch list, Sale-perspective)
  - `/control/sales/api/sales/?contract=&batch=` (JSON)
  - `/control/sales/<pk>/accept/` (POST), `/reject/`, `/bulk-accept/`, `/bulk-update/`
  - `/control/sales/export/`, `/control/sales/export-list/` (streaming CSV)
- `/control/settings/social-accounts/`, `/social-apps/` (CRUD), `/site/` — superuser only.
- `/control/settings/system/` — `system_settings` view; global toggles (auto_review_enabled). Superuser only.
- `/control/sync-log/` — superuser-only `SaleImport` debug view.

---

## 7. Auth & Permissions

### 7.1 User Types

| Type | Flags | Login redirect | Capabilities |
|---|---|---|---|
| **superuser** | `is_superuser=True, is_staff=True` | `/control/` | Everything; superuser-only routes (sync_log, social config, sites) |
| **staff** | `is_staff=True` | `/control/` | Per Group permissions (`@perm_required`) |
| **portal** | no flags + `UserProfile.account` | `/portal/dashboard/` | Read own pharmacy data only; gated by `Account.pharmacy_portal=True` |

`UserForm.save()` (`control/forms.py`) sets these flags. Portal users **must** have an Account; non-portal users have any UserProfile deleted; `user_permissions` is always cleared (Group-only model).

### 7.2 Decorators (`control/decorators.py`)

| Decorator | Behavior |
|---|---|
| `@staff_required` | Active + is_staff. Redirect to `/portal/login/` on miss. |
| `@perm_required('app.codename')` | Active + is_staff + permission (superusers bypass). 403 on miss. |
| `@superuser_required` | Active + is_staff + is_superuser. 403 on miss. |

### 7.3 Permission Codenames In Use

(don't invent new ones without adding the matching Django permission)

- `auth.{view,add,change,delete}_group`
- `auth.{view,add,change,delete}_user`
- `fidpha.{view,add,change,delete}_account`
- `fidpha.{view,add,change,delete}_contract`
- `fidpha.{view,add,change,delete}_product`
- `api.{view,add,change,delete}_apitoken` — `tokens_revoke`/`reactivate` use `change_apitoken`
- `sales.view_sale`, `sales.change_sale` — accept/reject/bulk all use `change_sale`

### 7.4 Portal Login Decision Tree (`custom_login`)

1. If staff → `/control/`.
2. Else read `user.profile.account`. If `account.pharmacy_portal == False` → reject.
3. Else → `/portal/dashboard/`.

### 7.5 Google OAuth — Fresh PostgreSQL DB Gotcha

When setting up a fresh PostgreSQL database (`migrate` + `loaddata`), the `SocialApp` for Google is linked to `site id=2` (the local dev site) but `SITE_ID=1` in settings. allauth's `get_app()` looks up by `SITE_ID` and raises `DoesNotExist` on `/auth/google/login/`.

**Fix — run once after `loaddata` on any new PG database:**
```python
from django.contrib.sites.models import Site
from allauth.socialaccount.models import SocialApp
app = SocialApp.objects.get(provider='google')
app.sites.add(Site.objects.get(id=1))
```

### 7.6 Google OAuth (`fidpha/adapters.py`)

`FIDPHASocialAccountAdapter.pre_social_login`:
- Reads `email` from Google extra_data; missing → reject.
- `User.objects.get(email=email)` — must already exist. We do **not** auto-create from OAuth (`SOCIALACCOUNT_AUTO_SIGNUP = False`).
- Re-runs the portal access check.
- `get_login_redirect_url`: stashes flash message, routes staff → `/admin/welcome/`, portal → `/portal/dashboard/`.

`FIDPHAAccountAdapter.add_message` is overridden to suppress all default allauth messages.

### 7.6 API Auth (`api/authentication.py`)

- Header: `Authorization: Token <raw>`.
- Look up by `sha256(raw).hexdigest()` against `APIToken.token`.
- On success: bump `usage_count` + `last_used_at`, write `APITokenUsageLog` row. Returns `(None, token)` — `request.user` stays anonymous, `request.auth` is the `APIToken`.
- DRF defaults wire it globally + `HasAPIToken`. Throttling: `APITokenThrottle` (scope `api_token`, dynamic rate from `SystemConfig.api_token_rate_limit` cached 60 s, keyed on token pk, `api/throttles.py`); `AnonRateThrottle` fallback for requests with no token.

---

## 8. Ingestion Pipeline (`sales/services.py:submit_sales_batch`)

Single ingestion entry point. Three stages inside one `transaction.atomic()`:

1. **Stage 1**: bulk-insert all rows into `SaleImport` (status=pending).
2. **Stage 2**: validate each row, set `status` + `rejection_reason`. Build accepted Sale list. Resolved `contract_product` is persisted on rejected rows too (audit display).
3. **Between 2 and 3**: if `SystemConfig.auto_review_enabled AND contract.account.auto_review_enabled`, stamp all accepted rows `STATUS_ACCEPTED`, `auto_reviewed=True`, `reviewed_at=now()`. Otherwise rows stay `STATUS_PENDING`.
4. **Stage 3**: `bulk_create` accepted Sale rows; update `Contract.last_sale_datetime` + `last_sync_at`.

Safeguards:
- **Idempotency**: `_response_from_existing_batch(batch_id)` at entry — if batch_id already exists in `SaleImport`, returns the stored result immediately (safe retries).
- `BatchTooLargeError` if `len(sales_data) > SystemConfig.max_batch_size` (cached 30 s; 0 = no limit).
- `select_for_update()` on Contract (with `select_related("account")`) inside the transaction → race-safe `last_sale_datetime` and account flag access.
- Contract re-validated as `status=active` inside the transaction → handles deactivation mid-sync.

Response shape includes `warnings[]`. Populated with `CONCURRENT_BATCH` code when other pending batches exist for the same contract.

Per-row rejection reasons (in order):
- Product not in active contract.
- `sale_datetime.date() >= today`.
- `sale_datetime <= contract.last_sale_datetime` (boundary exclusive).
- `creation_datetime > now` or `creation_datetime < sale_datetime`.
- `sale_datetime` outside `[contract.start_date, contract.end_date]`.
- `quantity <= 0` or `ppv <= 0`.

---

## 9. Migration Timeline

(All applied. No edits to applied migrations without a plan.)

| App | # | Effect |
|---|---|---|
| fidpha | 0001 | Initial: Account, UserProfile, Product, Contract, Contract_Product |
| fidpha | 0002 | Contract.start_date / end_date → DateTimeField |
| fidpha | 0003 | UserProfile.email_verified, verification_token, token_created_at |
| fidpha | 0004 | TraceableMixin fields on Account/Contract/Product/UserProfile |
| fidpha | 0005 | Contract.last_sync_at, last_sale_datetime |
| fidpha | 0006 | RoleProfile (Group icon) |
| fidpha | 0007 | Contract_Product.points_per_unit (default 1), target_quantity |
| fidpha | 0008 | **Product.ppv** added (nullable Decimal 10,2) |
| fidpha | 0009 / 0010 | Contract_Product.points_per_unit → Decimal(6,2) |
| fidpha | 0011 | **RoleProfile traceability** — adds TraceableMixin fields (created_by/at, modified_by/at) |
| api | 0001 | APIToken |
| api | 0002 | APIToken.created_by |
| api | 0003 | APITokenUsageLog |
| api | 0004 | **Token hashing** — token_suffix added; existing plain tokens hashed in-place via RunPython. `sha256(old_raw)` matches stored hash, so existing API clients keep working. |
| sales | 0001 | SaleImport, Sale |
| sales | 0002 | Quantity tweaks |
| sales | 0003 | **Sale.status** + reviewed_by/at (default pending) |
| sales | 0004 | Removed Sale unique_together |
| sales | 0005 | **Sale.product_ppv** added |
| sales | 0006 | **Backfill** Sale.product_ppv from contract_product.product.ppv |
| sales | 0007 | **Sale.rejection_reason** (CharField 500, blank, default="") — reviewer reason on manual reject |
| sales | 0008 | **Sale.auto_reviewed** (bool, default False) — auto-review audit flag |
| fidpha | 0012 | **Account.auto_review_enabled** (bool, default False) — per-account auto-review opt-in |
| control | 0001 | **SystemConfig** — first migration for control app; single-row global config table |
| control | 0002 | Alter SystemConfig.id → BigAutoField (Django 5.2 default) |
| control | 0003 | **SystemConfig new fields** — `max_batch_size`, `ppv_tolerance_percent`, `rejection_rate_warn_threshold`, `rejection_rate_danger_threshold`, `api_token_rate_limit` |
| control | 0004 | **SystemConfig default-off** — change all new field defaults to 0/None (disabled sentinel); RunPython resets existing singleton row |
| fidpha | 0013 | **Product.ppv NOT NULL** — RunSQL backfills NULL ppv rows to 0.00 (quoted `"Product"` table name for PostgreSQL case-sensitivity); AlterField makes ppv required |

---

## 10. Frontend Conventions

### CSS

- Single `fidpha/static/fidpha/css/portal.css` (shared portal + control). Control template layers per-page `<style>` blocks.
- Variables on `:root`: `--sidebar-bg`, `--card-bg`, `--card-border`, `--text-primary`, `--text-secondary`, `--accent` (`#1b679b`), `--accent-hover`, `--gold` (`#d8bd2e`), `--success`/`--warning`/`--danger`. Use these — never hardcode hex.
- Dark theme only. Light-theme toggle UI exists but is deferred.
- Standard classes: `.stat-card`, `.stat-label`/`-value`/`-sub`, `.badge-success`/`-warning`/`-danger`, `.grid-2`/`-3`/`-4`. Responsive: 1 col at ≤768px.

### JS

- No build step. Vanilla JS in `<script>` blocks at end of each template.
- ECharts loaded via CDN per template (SVG renderer).
- Material Icons Round + Inter from Google Fonts in `base.html`.
- Portal helpers: `static/fidpha/js/portal.js` (sidebar, theme).
- Admin-only JS (django-unfold pages): `static/admin/account_form.js`, `user_form.js`, `product_toggle.js`, `product_list.js`, `contract_form.js`. Loaded by `admin.py` `Media` classes — not used by control panel.

### Charts

- Full-option builder functions, e.g. `buildTrendMonthlyOpt()`, `buildProductOpt(labels, data)`.
- `chart.setOption(opt, true)` (notMerge=true) for swaps.
- Drill-down: `trendDrillActive` flag + back button + info span.
- Cross-chart filter: clicking a month in Monthly Trend filters Points-by-Product via `productsByMonth[mk]`. Implemented in `fidpha/templates/fidpha/contracts.html` and `control/templates/control/contracts_detail.html`.

### Template data bridge

- Views `json.dumps(...)` chart data and pass via `render(...)` context.
- Templates render with `{{ ... |safe }}` inside `<script>` literals.

### React conventions (`frontend/src/`)

- `api/client.js` — central fetch wrapper. Reads CSRF from `csrftoken` cookie, sets `credentials: "include"`, throws typed errors with `.status`. All portal API calls go through `apiFetch(path, options)` where `path` is relative to `/api/portal`.
- `components/Layout.jsx` — sidebar + `<Outlet />`. Nav items defined in `NAV` array. Logout via `fetch('/admin/logout/')` + redirect.
- Pages follow the pattern: parallel `apiFetch` calls in `useEffect`, `loading` / `error` guard, then render.
- ECharts: option-builder functions return plain objects (not JSX). `ReactECharts` component with `style={{ height: N }}`.
- No points math, no permission checks, no status derivation in frontend code — all comes from the API.
- In dev, basename is stripped — routes are `/dashboard`, `/contracts`, `/sales`, `/pharmacy`. In production (`/app/`), React handles routing client-side.

---

## 11. Common Patterns (Implementation Quirks)

- **PRG with session stash** for control forms: redirect on POST, hydrate from `request.session.pop("_<form>_<pk>")` on GET. See `accounts_create`, `contracts_edit`, `products_create`.
- **Audit logging**: `_log(user, obj, flag, msg)` (`control/views.py:36`) writes Django `LogEntry`. Use on every create/edit/delete in control panel.
- **TraceableMixin**: stamp `created_by` on creation, `modified_by` on edit, before save.
- **CSV export**: `StreamingHttpResponse` + generator. Don't build CSV in memory. See `sales_export_csv`, `sync_log` export branch.
- **Batch API endpoints**: return `{"items":[...], "total":..., "page":..., "pages":..., "has_prev":..., "has_next":...}`. Match shape.
- **`ContractProductFormSet`**: extended `BaseInlineFormSet` supports "delete and re-add same product" via `_skip_unique_pks`.
- **`_pending_cp_deletes` pattern**: `Contract.clean()` runs before `formset.save()` (standard Django validation order), so DB still contains rows that the formset will delete. `contracts_edit` parses `DELETE` checkboxes from `request.POST`, collects their CP PKs into `pending_deletes`, and sets `contract._pending_cp_deletes = pending_deletes` before `form.is_valid()`. `clean()` reads this attribute to exclude those rows from the inactive-product check.
- **Immediate unlink (contract form)**: The unlink button in Edit mode fires an AJAX POST to `contracts_unlink_product` which deletes the `Contract_Product` immediately. On success, JS removes the row from the DOM and calls `_reindexFormset()` to renumber remaining rows' `name`/`id` attributes and update `TOTAL_FORMS`. This avoids the DELETE-checkbox-but-still-in-DB inconsistency.
- **Contract products import modal**: client-side only (both Create and Edit mode). Parses CSV/JSON/Excel via `parseCpCsvText`/`parseCpJSON`/`parseCpExcel`. Shows editable preview. On submit, resolves product codes from `ALL_PRODUCTS` JS array (includes `code` field), checks against visible formset rows via `getUsedIds()`, then calls `addProductRow()` for each valid row. Skipped rows are shown with reasons and a Fix & retry button. Import button is gated to Edit mode + `change_contract` permission.

---

## 12. Settings / Security Notes

### Hardening completed on `feature/production-hardening`

Phase 1 production hardening — 6 commits. Each is independent and reversible:

- **Security headers** (`settings.py`): `SECURE_CONTENT_TYPE_NOSNIFF`, `SECURE_BROWSER_XSS_FILTER`, `SECURE_REFERRER_POLICY="same-origin"`, `X_FRAME_OPTIONS="DENY"`. HTTPS-gated set (`if not DEBUG`): `SECURE_SSL_REDIRECT`, `SECURE_HSTS_SECONDS=31536000` (+ subdomains + preload), `SECURE_PROXY_SSL_HEADER`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`. CSP intentionally deferred until React migration (templates use inline `<script>` blocks).
- **Production WSGI**: Gunicorn + WhiteNoise (`gunicorn.conf.py`, `WhiteNoiseMiddleware` after `SecurityMiddleware`, `STORAGES["staticfiles"]=CompressedManifestStaticFilesStorage`).
- **Logging**: structured `LOGGING` dict in `settings.py`. `python-json-logger` JSON formatter in prod, verbose plain-text in DEBUG. `wininpharma.*` namespace.
- **Health endpoint**: `/health/` checks db + cache + migrations. Unauthenticated, never cached.
- **Sentry**: env-gated init in `settings.py` (`if SENTRY_DSN`). `DjangoIntegration`, `traces_sample_rate=1.0` in DEBUG / `0.1` in prod, `send_default_pii=False`.
- **Redis (Upstash)**: env-gated CACHES + cached_db sessions (`if REDIS_URL`). Falls back to `LocMemCache` + DB sessions when empty. `KEY_PREFIX="wininpharma"`.
- **Doppler**: cloud secret store, dual-mode with `.env`. Use `doppler run -- <cmd>` to inject from cloud; bare command reads local `.env`. Both work independently. No code changes — `python-decouple` reads env-var first.

### Remaining known dev-only shortcuts (intentional; surface but don't silently fix)

- `settings.py` — `SECRET_KEY` defaults to `django-insecure-...` literal (still warned by `manage.py check --deploy`). Will be replaced by Doppler-managed strong key for production deploys.
- `settings.py` — `ALLOWED_HOSTS=*` (wildcard default). Restrict per-environment when deploying.
- `DB_BACKEND` in `.env` controls the active database: `sqlite` (default), `local` (localhost PostgreSQL), `neon` (cloud). Testing server (PythonAnywhere) uses `sqlite`. Switch with one line — no code change needed.
- `legacy_models.py` exists in `fidpha/`. **Inactive**, don't edit/import.

After Phase 1, `manage.py check --deploy` with `DEBUG=False` drops from **6 security warnings → 1** (only the SECRET_KEY warning remains).

---

## 13. Testing

### Test suite location

Tests live inside the Django repo at `tests-suite/`. Layout:

```
FIDPHA001/                    ← Django repo root
├── manage.py
├── pytest.ini                ← testpaths = tests-suite
└── tests-suite/
    ├── conftest.py           ← shared setup (DJANGO_ALLOW_ASYNC_UNSAFE for Playwright,
    │                            autouse SystemConfig + cache reset per test)
    ├── unit/
    │   ├── __init__.py
    │   ├── test_api.py
    │   ├── test_control.py
    │   ├── test_fidpha.py
    │   └── test_sales.py
    └── e2e/
        ├── __init__.py
        ├── conftest.py       ← Playwright + base_data fixtures
        └── test_*.py         ← 8 files
```

> The suite was relocated outside the repo on 2026-05-17 to keep production deploys lean, then moved back on 2026-05-22 ahead of Phase 2.2 (GitHub Actions CI) so CI checkouts include it. Space saving wasn't worth the dual-repo coordination cost.

### Unit Tests
- ~197 active tests collected from `tests-suite/unit/`.
- Run: `pytest --ignore=tests-suite/e2e` (from inside the repo)
- Current baseline (verified 2026-05-21 on Neon Postgres): **197 passed / 1 skipped / 0 failed**.
- The 1 skipped test is `test_same_contract_two_concurrent_batches` — deferred because the test's "both batches succeed" assertion conflicts with the strictly-after `last_sale_datetime` rule when thread ordering reverses. Production behavior is correct; the test needs a rewrite.

### E2E Tests (Playwright)
- **Status: Done** — 22 tests across 8 files, all passing on Neon Postgres + Chromium.
- Framework: `pytest-playwright` + `pytest-django`. Lives at `tests-suite/e2e/`.
- `DJANGO_ALLOW_ASYNC_UNSAFE=true` set in `tests-suite/conftest.py` (required for Playwright + Django live server).
- Run: `pytest tests-suite/e2e/` (from inside the repo)

| File | Tests | What's covered |
|---|---|---|
| `test_auth.py` | 4 | Login redirect (staff + portal), wrong-password error, logout |
| `test_portal.py` | 4 | Portal login → dashboard, stat cards, sales page, pharmacy name |
| `test_sales_review.py` | 4 | Batch list loads, accept sale, reject sale, accepted row leaves pending queue |
| `test_control_accounts.py` | 2 | Accounts list loads, create account → lands on detail page |
| `test_control_products.py` | 2 | Products list loads, create product → redirects to list with row |
| `test_control_contracts.py` | 2 | Contracts list loads, create contract → lands on detail page |
| `test_control_settings.py` | 2 | System settings page loads, toggle auto-review persists to DB |
| `test_control_tokens.py` | 2 | Tokens list loads, create token → plain value revealed in banner |

**Gotchas for future test authoring:**
- Sales list is a JS SPA — batches load via fetch into `#blRows`; sales table only appears inside a modal after clicking a batch row.
- Choices.js selects need `select_option(value, force=True)` to bypass visibility checks.
- `datetime-local` inputs require `"YYYY-MM-DDTHH:MM"` format (not `"YYYY-MM-DD"`).
- Base template renders nav links twice (desktop + mobile) → use `.first` on nav link locators.
- Language-switcher `[type=submit]` conflicts → always use `#submitBtn` for form submit buttons.
- `UserProfile` has no auto-creation signal — `UserProfile.objects.create(...)` explicitly in fixtures.
- `Contract.clean()` enforces one active contract per account — contract create tests need a fresh account.

---

## 14. Pending Work

- Apple OAuth provider.
- Token detail page enhancements (usage chart; `APITokenUsageLog` model already in place).
- `SystemConfig.ppv_tolerance_percent` enforcement — field is stored and configurable but the rejection check inside `submit_sales_batch` is still a no-op.
- Sales Review UX backlog (remaining items).
- React SPA (`feature/react-ui`) — portal and staff React UIs built, paused pending advisor approval to merge.

---

## 15. Key Files (file:line)

| Need | Location |
|---|---|
| Points calc (portal) | `fidpha/views.py:594` `_pts_qs()` |
| Points calc (control) | `control/views.py:958` `_pts_qs()` |
| Sales ingestion | `sales/services.py:47` `submit_sales_batch()` |
| PPV snapshot site | `sales/services.py:204` |
| Active contract lookup | `fidpha/services.py:101` |
| Bulk link products to contract | `fidpha/services.py:340` `bulk_link_products_to_contract()` |
| API token auth | `api/authentication.py` |
| API endpoints | `api/views.py`, `api/urls.py` |
| Control decorators | `control/decorators.py` |
| Audit log helper | `control/views.py:153` `_log()` |
| Immediate unlink endpoint | `control/views.py` `contracts_unlink_product` |
| Global config model | `control/models.py` `SystemConfig.get()` |
| Per-token throttle | `api/throttles.py` `APITokenThrottle` |
| Settings | `FIDPHA001/settings.py` |

---
**End of ARCHITECTURE.md.** Rules and decisions live in [CLAUDE.md](CLAUDE.md).
