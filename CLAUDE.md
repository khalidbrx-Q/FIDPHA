# CLAUDE.md — WinInPharma Contributor Guide

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
| `feature/react-ui` | React SPA (in progress — do not merge without approval) |
| `feature/i18n` | French translations for control panel (in progress) |

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

---

## 9. Common Commands

```bash
python manage.py runserver          # start Django dev server
python manage.py migrate            # apply migrations
python manage.py makemigrations     # create new migration
python manage.py compilemessages    # compile French translations
python manage.py collectstatic      # collect static files
```

---
**End.** When in doubt: read the code, follow the existing pattern, ask before breaking a rule.
