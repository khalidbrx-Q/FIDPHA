[English](#english) | [Français](#français)

---

<a name="english"></a>

# WinInPharma — Pharmacy Loyalty Platform

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [How It Works](#2-how-it-works)
3. [Tech Stack](#3-tech-stack)
4. [Local Setup](#4-local-setup)
5. [Pharmacy Portal](#5-pharmacy-portal)
6. [Staff Control Panel](#6-staff-control-panel)
7. [Public API](#7-public-api)
8. [Sales Ingestion Pipeline](#8-sales-ingestion-pipeline)
9. [Authentication & Permissions](#9-authentication--permissions)
10. [Deployment](#10-deployment)
11. [Project Structure](#11-project-structure)

---

## 1. Project Overview

**WinInPharma** is a pharmacy loyalty management platform built with Django. It connects a pharmaceutical company (the operator) with its pharmacy network through a points-based incentive system.

Pharmacies submit their daily sales data via an API. Each sale is validated against an active contract and earns the pharmacy a number of loyalty points, calculated from a per-product multiplier defined in the contract. Pharmacies log into a dedicated portal to track their points, view their contracts, and monitor their sales history. The operator's staff manage everything from a custom control panel.

### Key Features

| Feature | Description |
|---|---|
| Pharmacy portal | 4-page dashboard: stats + charts, contracts, points breakdown, account info |
| Staff control panel | Full CRUD for accounts, contracts, products, users, tokens; sales review workflow |
| Public REST API | Token-authenticated API for pharmacy machines to submit sales and query contracts |
| Points system | Per-product multiplier × quantity × PPV snapshot; computed server-side only |
| Auto-review | Configurable global + per-account automatic acceptance of valid sales |
| Sales ingestion | Batch pipeline with idempotency, race protection, concurrent batch warnings |
| Google OAuth | Pharmacy and staff users can log in with Google |
| Email system | HTML verification emails, password reset, WinInPharma branding |
| French i18n | Portal available in French (EN/FR toggle) |
| Audit trail | Every staff action logged via Django LogEntry; visible on control panel dashboard |
| CSV / Excel import | Bulk product import and contract product import via file upload |

---

## 2. How It Works

The platform has three user-facing layers:

```
┌─────────────────────────────────────────────────────────────────┐
│                        WinInPharma                              │
├─────────────────┬───────────────────────┬───────────────────────┤
│  Pharmacy Portal│   Staff Control Panel │    Public REST API     │
│  /portal/       │   /control/           │    /api/v1/            │
│                 │                       │                        │
│  Session auth   │   Session auth        │   Token auth           │
│  Pharmacy users │   Staff / superusers  │   Pharmacy machines    │
│                 │                       │   (external software)  │
└─────────────────┴───────────────────────┴───────────────────────┘
```

**Typical flow:**

1. Operator staff creates an Account (pharmacy) and assigns it an active Contract with products and point multipliers.
2. The pharmacy's software submits daily sales via `POST /api/v1/sales/` using a token.
3. The ingestion pipeline validates each row: checks the product is in the active contract, verifies the datetime, snapshots the PPV, and computes points.
4. Staff review pending sales in the control panel (accept / reject with reason / bulk actions). Auto-review can be enabled to skip this step.
5. The pharmacy's portal user logs in and sees their points, contract details, and charts.

---

## 3. Tech Stack

| Concern | Choice |
|---|---|
| Backend | Python 3.12, Django 5.2 |
| Database | SQLite (dev) — upgradeable |
| REST API | Django REST Framework (partial adoption — no viewsets/routers) |
| Authentication | django-allauth (Google OAuth + email/password) |
| Admin theme | django-unfold (dormant — replaced by control panel) |
| Frontend | Vanilla JS + ECharts (CDN) + Material Icons + Inter font |
| CSS | Single `portal.css` shared by portal and control panel |
| Email | Gmail SMTP — `EmailMultiAlternatives` (HTML + text) |
| i18n | Django i18n + GNU gettext, `locale/fr/` |
| Deployment | PythonAnywhere + GitHub (PR-based workflow) |
| React SPA | Vite 6 + React 18 + shadcn/ui + Tailwind (in progress, `feature/react-ui`) |

---

## 4. Local Setup

### 4.1 Prerequisites

- Python 3.12
- Git
- GNU gettext (for translation compilation — Windows: `C:\Program Files\gettext-iconv\bin`)

### 4.2 Clone & Install

```bash
git clone https://github.com/khalidbrx-Q/FIDPHA.git
cd FIDPHA
python -m venv .venv

# Windows
.venv\Scripts\activate
# Mac/Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 4.3 Environment Variables

Create a `.env` file in `FIDPHA/` (same folder as `manage.py`):

```
SECRET_KEY=your-secret-key
DEBUG=True
EMAIL_HOST_USER=your@gmail.com
EMAIL_HOST_PASSWORD=your-gmail-app-password
DEFAULT_FROM_EMAIL=WinInPharma <your@gmail.com>
```

### 4.4 Initialize the Database

```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py compilemessages   # compile French translations
python manage.py runserver
```

Visit `http://127.0.0.1:8000` — you will be redirected to `/portal/login/`.

Log in with your superuser account to access the control panel at `/control/`.

---

## 5. Pharmacy Portal

The portal is the pharmacy-facing interface. Only users with `Account.pharmacy_portal = True` can access it.

### Pages

| Page | URL | Description |
|---|---|---|
| Dashboard | `/portal/dashboard/` | KPI cards (points, units, contracts, pending sales) + 4 ECharts charts (monthly trend, cumulative, units, top products) |
| Contracts | `/portal/contracts/` | Active contract products table + monthly trend chart with daily drill-down + cross-chart filter |
| Points | `/portal/sales/` | Full sales table with status filter, product search, acceptance rate, year selector |
| Pharmacy | `/portal/pharmacy/` | Account info, edit profile, change password, email verification status |

### Authentication Flow

```
User visits / → redirected to /portal/login/
↓
Enters credentials (or signs in with Google)
↓
Staff user → /control/
Portal user (pharmacy_portal=True) → /portal/dashboard/
```

### Email Verification

New pharmacy users must verify their email before accessing the portal:

```
First login → /portal/setup-profile/ (enter email + optional name/password)
→ Verification email sent (24h token)
→ User clicks link → email_verified = True → full portal access
```

### Points Formula

Points are always computed server-side using this formula:

```
points = round(quantity × Sale.product_ppv × Contract_Product.points_per_unit)
```

- `Sale.product_ppv` is a snapshot of `Product.ppv` taken at the moment of ingestion.
- This value is frozen — it never changes even if the catalog price changes later.
- The frontend only displays — it never recomputes.

---

## 6. Staff Control Panel

The control panel at `/control/` replaces Django admin entirely. It is accessible to `is_staff=True` users. Superusers have full access; regular staff see only what their permissions allow.

### Modules

| Module | URL | What you can do |
|---|---|---|
| Dashboard | `/control/` | Activity feed (25 most recent actions), quick stats |
| Roles | `/control/roles/` | Create/edit Django Groups with icon and permissions |
| Users | `/control/users/` | Create/edit superusers, staff, and portal (pharmacy) users |
| Accounts | `/control/accounts/` | Full CRUD for pharmacies; auto-generate account codes |
| Contracts | `/control/contracts/` | Full CRUD; inline product management with CSV/Excel/JSON import modal; trend charts |
| Products | `/control/products/` | Full CRUD; bulk CSV import (`/control/products/import/`) |
| API Tokens | `/control/tokens/` | Create tokens (shown once, stored as SHA-256 hash); revoke/reactivate; 30-day usage chart |
| Sales Review | `/control/sales/` | Batch list, inline sale expansion, accept/reject with reason, bulk actions, CSV export |
| System Settings | `/control/settings/system/` | Global auto-review toggle (superuser only) |
| Social / Sites | `/control/settings/social-apps/` etc. | Google OAuth app config, Django Sites (superuser only) |

### Sales Review Workflow

```
Pharmacy submits sales via API
       ↓
Sales land in the database with status=PENDING
       ↓
Staff opens /control/sales/ → selects a batch → reviews individual rows
       ↓
Accept → status=ACCEPTED, points counted
Reject → status=REJECTED, rejection_reason recorded
       ↓
Or: enable Auto-Review (global + per-account) to skip manual review
```

### Auto-Review

Two switches must both be ON for auto-review to activate:

1. **Global**: `SystemConfig.auto_review_enabled` (set in System Settings)
2. **Per-account**: `Account.auto_review_enabled` (set in Account edit form)

When both are ON, valid sales are automatically accepted on ingestion. `Sale.auto_reviewed = True` marks these rows; `reviewed_by` remains None.

### Contract Products Import

Inside the contract edit form, staff can import products via a modal:

- Supported formats: **CSV** (comma or semicolon separated), **Excel** (.xlsx / .xls), **JSON**
- Shows an editable preview before adding rows to the formset
- Skipped rows are shown with the skip reason and a "Fix & retry" option
- Available in Edit mode only (requires `change_contract` permission)

---

## 7. Public API

The public API at `/api/v1/` is consumed by external pharmacy software (not browsers). Every request must include a valid API token.

### Authentication

```
Authorization: Token YOUR_RAW_TOKEN
```

Tokens are created in the control panel (`/control/tokens/`). The raw token is shown **once** at creation; it is stored as a SHA-256 hash — it cannot be recovered later.

### Endpoints

#### GET /api/v1/contract/active/

Returns the active contract for a given pharmacy account.

**Query parameter:** `account_code` (required)

**Success response (200):**
```json
{
    "status": "success",
    "timestamp": "2026-05-11T10:00:00Z",
    "contract": {
        "id": 1,
        "pharmacy": "PHARMACY SAADA",
        "account_code": "PH-00001",
        "start_date": "2026-04-01T00:00:00Z",
        "end_date": "2026-06-30T23:59:59Z",
        "products": [
            {
                "product_id": 1,
                "internal_code": "MED-001",
                "external_designation": "DOLI1000",
                "points_per_unit": "1.50",
                "target_quantity": 200
            }
        ]
    }
}
```

#### POST /api/v1/sales/

Submits a batch of sales records.

**Request body:**
```json
{
    "account_code": "PH-00001",
    "batch_id": "unique-batch-uuid",
    "sales": [
        {
            "external_designation": "DOLI1000",
            "sale_datetime": "2026-05-10T14:00:00",
            "creation_datetime": "2026-05-10T14:01:00",
            "quantity": 10,
            "ppv": 12.50
        }
    ]
}
```

**Success response (200):**
```json
{
    "status": "success",
    "accepted": 8,
    "rejected": 2,
    "pending": 0,
    "warnings": [],
    "rejections": [
        {
            "row": 3,
            "reason": "sale_datetime is not within contract period"
        }
    ]
}
```

**Error codes:**

| Code | HTTP | Meaning |
|---|---|---|
| `INVALID_TOKEN` | 401 | Token missing or inactive |
| `MISSING_FIELD` | 400 | Required field absent |
| `ACCOUNT_NOT_FOUND` | 404 | No account with that code |
| `CONTRACT_NOT_FOUND` | 404 | No active contract for account |
| `BATCH_TOO_LARGE` | 400 | Batch exceeds 50,000 rows |
| `SERVER_ERROR` | 500 | Internal error |

### Rate Limiting

1,000 requests per hour per token. Throttle scope: `api_token` (keyed on token PK).

---

## 8. Sales Ingestion Pipeline

When `POST /api/v1/sales/` is called, `submit_sales_batch()` in `sales/services.py` runs:

1. **Idempotency check** — if `batch_id` already exists, return the stored result immediately (safe retries).
2. **Batch size check** — reject if > 50,000 rows.
3. **Atomic transaction** with `select_for_update()` on the contract:
   - Bulk-insert all rows into `SaleImport` (status=pending).
   - Validate each row (product in contract? datetime valid? quantity/ppv positive?).
   - If auto-review is enabled for this account: auto-accept valid rows.
   - Bulk-create accepted `Sale` rows with PPV snapshot.
   - Update `Contract.last_sale_datetime`.
4. **Concurrent batch warning** — if other pending batches exist for the same contract, a `CONCURRENT_BATCH` warning is included in the response.

**Per-row rejection reasons (in order):**
- Product not in active contract
- `sale_datetime.date() >= today` (no same-day or future sales)
- `sale_datetime <= contract.last_sale_datetime` (boundary exclusive)
- `creation_datetime` out of range
- `sale_datetime` outside contract period
- `quantity <= 0` or `ppv <= 0`

---

## 9. Authentication & Permissions

### User Types

| Type | Django flags | Logs into | Can access |
|---|---|---|---|
| **Superuser** | `is_superuser=True, is_staff=True` | `/control/` | Everything, including system settings |
| **Staff** | `is_staff=True` | `/control/` | Modules allowed by their Role (Group permissions) |
| **Portal user** | no flags + `UserProfile` linked to `Account` | `/portal/` | Own pharmacy data only |

### Roles & Permissions

Staff permissions are managed through Django Groups (called "Roles" in the control panel). Each role has an icon and a set of Django permissions. Staff users are assigned to one or more roles — they can only access the control panel modules covered by their permissions.

### Google OAuth

- Pharmacy and staff users can sign in with Google.
- Google login **does not create new accounts** — the user must already exist in the system.
- The same access rules apply: `pharmacy_portal=True` for portal users, `is_staff=True` for staff.

---

## 10. Deployment

### 10.1 Branch Strategy

| Branch | Purpose |
|---|---|
| `main` | Production — deployed to PythonAnywhere |
| `develop` | Active backend development |
| `feature/react-ui` | React SPA (in progress — not merged to main) |
| `feature/i18n` | French translations for control panel (in progress) |

### 10.2 Merging to Main (via GitHub PR)

Never merge locally. Always use a GitHub Pull Request:

```
git push origin develop
→ Open PR on GitHub (develop → main)
→ REPO REVIEWER routine fires (automated security + bug scan)
→ Read the review report
→ Click "Merge pull request" on GitHub
```

The **REPO REVIEWER** is a Claude Code routine that automatically reviews every PR diff for security vulnerabilities and bugs, then posts a verdict comment on the PR.

### 10.3 Updating PythonAnywhere

After merging to `main`, open a Bash console on PythonAnywhere:

```bash
cd FIDPHA
workon fidpha
git checkout -- .           # discard any local server edits
git pull origin main
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py compilemessages
```

Then go to **Web tab → Reload**.

### 10.4 First-Time PythonAnywhere Setup

```bash
git clone https://github.com/khalidbrx-Q/FIDPHA.git
cd FIDPHA
mkvirtualenv fidpha --python=python3.12
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py createsuperuser
python manage.py compilemessages
```

Configure the web app (Web tab → Manual configuration → Python 3.12):

**WSGI file:**
```python
import sys, os

path = '/home/khalidbrx/FIDPHA'
if path not in sys.path:
    sys.path.insert(0, path)

os.environ['DJANGO_SETTINGS_MODULE'] = 'FIDPHA001.settings'

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
```

**Static files:**

| URL | Directory |
|---|---|
| `/static/` | `/home/khalidbrx/FIDPHA/staticfiles` |

**Virtualenv:** `/home/khalidbrx/.virtualenvs/fidpha`

### 10.5 Google OAuth for Production

In Google Cloud Console:
- Authorized origin: `https://khalidbrx.pythonanywhere.com`
- Redirect URI: `https://khalidbrx.pythonanywhere.com/auth/google/login/callback/`

In control panel → Social Apps → update domain and OAuth credentials.

### Live Demo

🌐 [khalidbrx.pythonanywhere.com](https://khalidbrx.pythonanywhere.com)

---

## 11. Project Structure

```
FIDPHA/                             ← git root (manage.py is here)
├── CLAUDE.md                       ← development rules and decisions
├── ARCHITECTURE.md                 ← deep technical reference
├── manage.py
├── db.sqlite3                      ← SQLite database (dev only, gitignored)
├── requirements.txt
├── FIDPHA001/                      ← Django project package
│   ├── settings.py
│   ├── urls.py                     ← root URL configuration
│   ├── wsgi.py
│   └── test_runner.py
├── fidpha/                         ← core app (models, portal views, services)
│   ├── models.py                   ← Account, UserProfile, Product, Contract, Contract_Product
│   ├── views.py                    ← portal views (dashboard, contracts, sales, pharmacy)
│   ├── services.py                 ← business logic (get_active_contract, bulk_import_products, ...)
│   ├── adapters.py                 ← Google OAuth adapter
│   ├── urls.py                     ← /portal/* routes
│   ├── static/fidpha/css/
│   │   ├── portal.css              ← shared CSS (portal + control panel)
│   │   └── login.css
│   └── templates/fidpha/           ← portal HTML templates + email templates
├── api/                            ← REST API layer
│   ├── models.py                   ← APIToken, APITokenUsageLog
│   ├── authentication.py           ← SHA-256 token authentication
│   ├── views.py                    ← /api/v1/ endpoints
│   ├── portal_views.py             ← /api/portal/ endpoints (React pharmacy portal)
│   ├── staff_views.py              ← /api/staff/ endpoints (React control panel)
│   ├── serializers.py              ← DRF serializers for portal + staff APIs
│   ├── permissions.py              ← HasAPIToken, PortalSessionPermission, StaffSessionPermission
│   └── throttles.py                ← per-token rate limiting
├── sales/                          ← ingestion + sale storage
│   ├── models.py                   ← SaleImport (raw), Sale (validated + points)
│   └── services.py                 ← submit_sales_batch() — single ingestion entry point
├── control/                        ← staff control panel
│   ├── models.py                   ← SystemConfig (global settings)
│   ├── views.py                    ← all control panel views (CRUD + sales review)
│   ├── forms.py                    ← all forms and formsets
│   ├── decorators.py               ← @staff_required, @perm_required, @superuser_required
│   └── templates/control/          ← control panel HTML templates
├── locale/fr/LC_MESSAGES/          ← French translations (.po source + .mo compiled)
├── static/                         ← global static (admin.css, admin JS)
├── templates/
│   ├── registration/               ← password reset templates
│   └── react/                      ← SPA shell templates (index.html, staff_index.html)
└── frontend/                       ← React SPA (feature/react-ui branch only)
    ├── src/
    │   ├── api/client.js           ← fetch wrapper (session + CSRF)
    │   ├── components/Layout.jsx
    │   └── pages/                  ← Dashboard, Contracts, Points, Pharmacy
    ├── vite.config.js
    └── package.json
```

---

*WinInPharma Documentation — May 2026*

---
---

[English](#english) | [Français](#français)

---

<a name="français"></a>

# WinInPharma — Plateforme de Fidélisation des Pharmacies

## Table des Matières

1. [Présentation du Projet](#1-présentation-du-projet)
2. [Fonctionnement](#2-fonctionnement)
3. [Stack Technique](#3-stack-technique)
4. [Installation Locale](#4-installation-locale)
5. [Portail Pharmacie](#5-portail-pharmacie)
6. [Panneau de Contrôle Staff](#6-panneau-de-contrôle-staff)
7. [API Publique](#7-api-publique)
8. [Pipeline d'Ingestion des Ventes](#8-pipeline-dingestion-des-ventes)
9. [Authentification & Permissions](#9-authentification--permissions)
10. [Déploiement](#10-déploiement)
11. [Structure du Projet](#11-structure-du-projet)

---

## 1. Présentation du Projet

**WinInPharma** est une plateforme de gestion de la fidélisation des pharmacies construite avec Django. Elle connecte une entreprise pharmaceutique (l'opérateur) à son réseau de pharmacies via un système d'incitation basé sur des points.

Les pharmacies soumettent leurs ventes quotidiennes via une API. Chaque vente est validée par rapport à un contrat actif et rapporte à la pharmacie un certain nombre de points de fidélité, calculés à partir d'un multiplicateur par produit défini dans le contrat. Les pharmacies se connectent à un portail dédié pour suivre leurs points, consulter leurs contrats et voir l'historique de leurs ventes. Le personnel de l'opérateur gère tout depuis un panneau de contrôle personnalisé.

### Fonctionnalités Clés

| Fonctionnalité | Description |
|---|---|
| Portail pharmacie | 4 pages : statistiques + graphiques, contrats, détail des points, infos compte |
| Panneau de contrôle staff | CRUD complet : comptes, contrats, produits, utilisateurs, tokens ; revue des ventes |
| API REST publique | API par token pour que les logiciels des pharmacies soumettent des ventes et interrogent les contrats |
| Système de points | Multiplicateur par produit × quantité × snapshot PPV ; calculé côté serveur uniquement |
| Auto-révision | Acceptation automatique configurable (global + par compte) des ventes valides |
| Ingestion des ventes | Pipeline par lots avec idempotence, protection aux conditions de course, avertissements de lots concurrents |
| Google OAuth | Connexion avec Google pour les pharmacies et le personnel |
| Système d'email | Emails HTML de vérification, réinitialisation de mot de passe, branding WinInPharma |
| i18n Français | Portail disponible en français (bascule FR/EN) |
| Piste d'audit | Chaque action staff enregistrée via Django LogEntry ; visible sur le tableau de bord |
| Import CSV / Excel | Import en masse de produits et de produits de contrats par fichier |

---

## 2. Fonctionnement

La plateforme comporte trois couches orientées utilisateur :

```
┌─────────────────────────────────────────────────────────────────┐
│                        WinInPharma                              │
├─────────────────┬───────────────────────┬───────────────────────┤
│ Portail Pharma  │ Panneau Contrôle Staff│    API REST Publique   │
│  /portal/       │   /control/           │    /api/v1/            │
│                 │                       │                        │
│  Auth session   │   Auth session        │   Auth par token       │
│  Utilisateurs   │   Staff / superusers  │   Logiciels pharmacie  │
│  pharmacie      │                       │   (logiciels externes) │
└─────────────────┴───────────────────────┴───────────────────────┘
```

**Flux typique :**

1. Le staff crée un Compte (pharmacie) et lui assigne un Contrat actif avec des produits et des multiplicateurs de points.
2. Le logiciel de la pharmacie soumet les ventes quotidiennes via `POST /api/v1/sales/` avec un token.
3. Le pipeline valide chaque ligne : vérifie que le produit est dans le contrat actif, contrôle la date, prend un snapshot du PPV et calcule les points.
4. Le staff examine les ventes en attente dans le panneau de contrôle (accepter / rejeter avec motif / actions groupées). L'auto-révision peut être activée pour ignorer cette étape.
5. L'utilisateur portail de la pharmacie se connecte et consulte ses points, ses contrats et ses graphiques.

---

## 3. Stack Technique

| Concern | Choix |
|---|---|
| Backend | Python 3.12, Django 5.2 |
| Base de données | SQLite (dev) — évolutif |
| API REST | Django REST Framework (adoption partielle — pas de viewsets/routers) |
| Authentification | django-allauth (Google OAuth + email/mot de passe) |
| Thème admin | django-unfold (inactif — remplacé par le panneau de contrôle) |
| Frontend | JS vanilla + ECharts (CDN) + Material Icons + Inter |
| CSS | `portal.css` unique partagé portail et panneau de contrôle |
| Email | Gmail SMTP — `EmailMultiAlternatives` (HTML + texte) |
| i18n | Django i18n + GNU gettext, `locale/fr/` |
| Déploiement | PythonAnywhere + GitHub (workflow par PR) |
| React SPA | Vite 6 + React 18 + shadcn/ui + Tailwind (en cours, `feature/react-ui`) |

---

## 4. Installation Locale

### 4.1 Prérequis

- Python 3.12
- Git
- GNU gettext (pour compiler les traductions — Windows : `C:\Program Files\gettext-iconv\bin`)

### 4.2 Cloner & Installer

```bash
git clone https://github.com/khalidbrx-Q/FIDPHA.git
cd FIDPHA
python -m venv .venv

# Windows
.venv\Scripts\activate
# Mac/Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 4.3 Variables d'Environnement

Créer un fichier `.env` dans `FIDPHA/` (même dossier que `manage.py`) :

```
SECRET_KEY=votre-secret-key
DEBUG=True
EMAIL_HOST_USER=votre@gmail.com
EMAIL_HOST_PASSWORD=votre-mot-de-passe-application
DEFAULT_FROM_EMAIL=WinInPharma <votre@gmail.com>
```

### 4.4 Initialiser la Base de Données

```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py compilemessages   # compiler les traductions françaises
python manage.py runserver
```

Visitez `http://127.0.0.1:8000` — vous serez redirigé vers `/portal/login/`.

Connectez-vous avec votre compte superuser pour accéder au panneau de contrôle `/control/`.

---

## 5. Portail Pharmacie

Le portail est l'interface destinée aux pharmacies. Seuls les utilisateurs avec `Account.pharmacy_portal = True` peuvent y accéder.

### Pages

| Page | URL | Description |
|---|---|---|
| Tableau de bord | `/portal/dashboard/` | KPI (points, unités, contrats, ventes en attente) + 4 graphiques ECharts |
| Contrats | `/portal/contracts/` | Tableau des produits du contrat actif + graphique mensuel avec drill-down quotidien |
| Points | `/portal/sales/` | Tableau complet des ventes avec filtre de statut, recherche de produit, taux d'acceptation, sélecteur d'année |
| Pharmacie | `/portal/pharmacy/` | Infos compte, modifier le profil, changer le mot de passe, statut de vérification email |

### Flux d'Authentification

```
Utilisateur visite / → redirigé vers /portal/login/
↓
Saisit ses identifiants (ou se connecte avec Google)
↓
Utilisateur staff → /control/
Utilisateur portail (pharmacy_portal=True) → /portal/dashboard/
```

### Vérification Email

Les nouveaux utilisateurs pharmacie doivent vérifier leur email avant d'accéder au portail :

```
Première connexion → /portal/setup-profile/ (saisie email + nom/mot de passe optionnels)
→ Email de vérification envoyé (token valable 24h)
→ Clic sur le lien → email_verified = True → accès complet au portail
```

### Formule des Points

Les points sont toujours calculés côté serveur avec cette formule :

```
points = round(quantité × Sale.product_ppv × Contract_Product.points_per_unit)
```

- `Sale.product_ppv` est un snapshot de `Product.ppv` pris au moment de l'ingestion.
- Cette valeur est figée — elle ne change jamais même si le prix catalogue évolue.
- Le frontend affiche uniquement — il ne recalcule jamais.

---

## 6. Panneau de Contrôle Staff

Le panneau de contrôle `/control/` remplace complètement Django admin. Il est accessible aux utilisateurs `is_staff=True`. Les superutilisateurs ont un accès total ; le staff classique voit uniquement ce que ses permissions autorisent.

### Modules

| Module | URL | Ce que vous pouvez faire |
|---|---|---|
| Tableau de bord | `/control/` | Fil d'activité (25 dernières actions), statistiques rapides |
| Rôles | `/control/roles/` | Créer/modifier des groupes Django avec icône et permissions |
| Utilisateurs | `/control/users/` | Créer/modifier superusers, staff et utilisateurs portail |
| Comptes | `/control/accounts/` | CRUD complet pour les pharmacies ; génération automatique de codes |
| Contrats | `/control/contracts/` | CRUD complet ; gestion inline des produits avec modal d'import CSV/Excel/JSON |
| Produits | `/control/products/` | CRUD complet ; import CSV en masse |
| Tokens API | `/control/tokens/` | Créer des tokens (affichés une fois, stockés en SHA-256) ; révoquer/réactiver |
| Revue des ventes | `/control/sales/` | Liste des lots, expansion inline, accepter/rejeter avec motif, actions groupées, export CSV |
| Paramètres système | `/control/settings/system/` | Bascule auto-révision globale (superuser uniquement) |
| Social / Sites | `/control/settings/social-apps/` etc. | Config OAuth Google, Django Sites (superuser uniquement) |

### Workflow de Revue des Ventes

```
La pharmacie soumet des ventes via l'API
       ↓
Les ventes arrivent en base avec status=PENDING
       ↓
Le staff ouvre /control/sales/ → sélectionne un lot → examine les lignes
       ↓
Accepter → status=ACCEPTED, points comptabilisés
Rejeter → status=REJECTED, motif de rejet enregistré
       ↓
Ou : activer l'Auto-Révision (global + par compte) pour ignorer la revue manuelle
```

### Auto-Révision

Deux interrupteurs doivent être tous les deux activés :

1. **Global** : `SystemConfig.auto_review_enabled` (dans Paramètres Système)
2. **Par compte** : `Account.auto_review_enabled` (dans le formulaire d'édition du compte)

Quand les deux sont actifs, les ventes valides sont automatiquement acceptées à l'ingestion. `Sale.auto_reviewed = True` marque ces lignes ; `reviewed_by` reste None.

### Import de Produits dans un Contrat

Dans le formulaire d'édition du contrat, le staff peut importer des produits via un modal :

- Formats supportés : **CSV** (séparateur virgule ou point-virgule), **Excel** (.xlsx / .xls), **JSON**
- Affiche un aperçu modifiable avant d'ajouter les lignes au formset
- Les lignes ignorées sont affichées avec le motif et un bouton "Corriger & réessayer"
- Disponible en mode Édition uniquement (nécessite la permission `change_contract`)

---

## 7. API Publique

L'API publique `/api/v1/` est consommée par les logiciels externes des pharmacies (pas les navigateurs). Chaque requête doit inclure un token API valide.

### Authentification

```
Authorization: Token VOTRE_TOKEN_BRUT
```

Les tokens sont créés dans le panneau de contrôle (`/control/tokens/`). Le token brut est affiché **une seule fois** à la création ; il est stocké sous forme de hash SHA-256 — il ne peut pas être récupéré ensuite.

### Endpoints

#### GET /api/v1/contract/active/

Retourne le contrat actif d'un compte pharmacie donné.

**Paramètre :** `account_code` (obligatoire)

**Réponse succès (200) :**
```json
{
    "status": "success",
    "timestamp": "2026-05-11T10:00:00Z",
    "contract": {
        "id": 1,
        "pharmacy": "PHARMACY SAADA",
        "account_code": "PH-00001",
        "start_date": "2026-04-01T00:00:00Z",
        "end_date": "2026-06-30T23:59:59Z",
        "products": [
            {
                "product_id": 1,
                "internal_code": "MED-001",
                "external_designation": "DOLI1000",
                "points_per_unit": "1.50",
                "target_quantity": 200
            }
        ]
    }
}
```

#### POST /api/v1/sales/

Soumet un lot de ventes.

**Corps de la requête :**
```json
{
    "account_code": "PH-00001",
    "batch_id": "uuid-unique-du-lot",
    "sales": [
        {
            "external_designation": "DOLI1000",
            "sale_datetime": "2026-05-10T14:00:00",
            "creation_datetime": "2026-05-10T14:01:00",
            "quantity": 10,
            "ppv": 12.50
        }
    ]
}
```

**Codes d'erreur :**

| Code | HTTP | Signification |
|---|---|---|
| `INVALID_TOKEN` | 401 | Token absent ou inactif |
| `MISSING_FIELD` | 400 | Champ requis absent |
| `ACCOUNT_NOT_FOUND` | 404 | Aucun compte avec ce code |
| `CONTRACT_NOT_FOUND` | 404 | Aucun contrat actif pour ce compte |
| `BATCH_TOO_LARGE` | 400 | Lot dépassant 50 000 lignes |
| `SERVER_ERROR` | 500 | Erreur interne |

### Limite de Débit

1 000 requêtes par heure par token. Scope du throttle : `api_token` (clé = PK du token).

---

## 8. Pipeline d'Ingestion des Ventes

Lors d'un appel `POST /api/v1/sales/`, `submit_sales_batch()` dans `sales/services.py` s'exécute :

1. **Vérification d'idempotence** — si `batch_id` existe déjà, retourner le résultat stocké immédiatement (retries sécurisés).
2. **Vérification de taille** — rejet si > 50 000 lignes.
3. **Transaction atomique** avec `select_for_update()` sur le contrat :
   - Insertion en masse de toutes les lignes dans `SaleImport` (status=pending).
   - Validation de chaque ligne (produit dans le contrat ? date valide ? quantité/ppv positifs ?).
   - Si l'auto-révision est activée pour ce compte : acceptation automatique des lignes valides.
   - Création en masse des lignes `Sale` acceptées avec snapshot PPV.
   - Mise à jour de `Contract.last_sale_datetime`.
4. **Avertissement lot concurrent** — si d'autres lots en attente existent pour le même contrat, un avertissement `CONCURRENT_BATCH` est inclus dans la réponse.

**Motifs de rejet par ligne (dans l'ordre) :**
- Produit absent du contrat actif
- `sale_datetime.date() >= aujourd'hui` (pas de ventes le jour même ou dans le futur)
- `sale_datetime <= contract.last_sale_datetime` (borne exclusive)
- `creation_datetime` hors plage
- `sale_datetime` hors période du contrat
- `quantity <= 0` ou `ppv <= 0`

---

## 9. Authentification & Permissions

### Types d'Utilisateurs

| Type | Flags Django | Se connecte à | Peut accéder à |
|---|---|---|---|
| **Superuser** | `is_superuser=True, is_staff=True` | `/control/` | Tout, y compris les paramètres système |
| **Staff** | `is_staff=True` | `/control/` | Modules autorisés par son Rôle (permissions de groupe) |
| **Utilisateur portail** | pas de flags + `UserProfile` lié à un `Account` | `/portal/` | Ses propres données pharmacie uniquement |

### Rôles & Permissions

Les permissions du staff sont gérées via les groupes Django (appelés "Rôles" dans le panneau de contrôle). Chaque rôle a une icône et un ensemble de permissions Django. Les utilisateurs staff sont assignés à un ou plusieurs rôles — ils n'accèdent qu'aux modules couverts par leurs permissions.

### Google OAuth

- Les utilisateurs pharmacie et staff peuvent se connecter avec Google.
- La connexion Google **ne crée pas de nouveaux comptes** — l'utilisateur doit déjà exister dans le système.
- Les mêmes règles d'accès s'appliquent : `pharmacy_portal=True` pour les utilisateurs portail, `is_staff=True` pour le staff.

---

## 10. Déploiement

### 10.1 Stratégie de Branches

| Branche | Rôle |
|---|---|
| `main` | Production — déployée sur PythonAnywhere |
| `develop` | Développement backend actif |
| `feature/react-ui` | SPA React (en cours — non mergée sur main) |
| `feature/i18n` | Traductions françaises du panneau de contrôle (en cours) |

### 10.2 Merger sur Main (via GitHub PR)

Ne jamais merger localement. Toujours passer par une Pull Request GitHub :

```
git push origin develop
→ Ouvrir une PR sur GitHub (develop → main)
→ La routine REPO REVIEWER se déclenche (analyse automatique de sécurité + bugs)
→ Lire le rapport de revue
→ Cliquer "Merge pull request" sur GitHub
```

Le **REPO REVIEWER** est une routine Claude Code qui analyse automatiquement chaque diff de PR pour détecter les vulnérabilités de sécurité et les bugs, puis publie un commentaire de verdict sur la PR.

### 10.3 Mettre à Jour PythonAnywhere

Après avoir mergé sur `main`, ouvrir une console Bash sur PythonAnywhere :

```bash
cd FIDPHA
workon fidpha
git checkout -- .           # annuler les modifications locales du serveur
git pull origin main
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py compilemessages
```

Puis aller dans l'onglet **Web → Reload**.

### 10.4 Installation Initiale sur PythonAnywhere

```bash
git clone https://github.com/khalidbrx-Q/FIDPHA.git
cd FIDPHA
mkvirtualenv fidpha --python=python3.12
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py createsuperuser
python manage.py compilemessages
```

Configurer l'application web (onglet Web → Configuration manuelle → Python 3.12) :

**Fichier WSGI :**
```python
import sys, os

path = '/home/khalidbrx/FIDPHA'
if path not in sys.path:
    sys.path.insert(0, path)

os.environ['DJANGO_SETTINGS_MODULE'] = 'FIDPHA001.settings'

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
```

**Fichiers statiques :**

| URL | Répertoire |
|---|---|
| `/static/` | `/home/khalidbrx/FIDPHA/staticfiles` |

**Virtualenv :** `/home/khalidbrx/.virtualenvs/fidpha`

### 10.5 Google OAuth pour la Production

Dans Google Cloud Console :
- Origine autorisée : `https://khalidbrx.pythonanywhere.com`
- URI de redirection : `https://khalidbrx.pythonanywhere.com/auth/google/login/callback/`

Dans le panneau de contrôle → Applications Sociales → mettre à jour le domaine et les identifiants OAuth.

### Démo en Ligne

🌐 [khalidbrx.pythonanywhere.com](https://khalidbrx.pythonanywhere.com)

---

## 11. Structure du Projet

```
FIDPHA/                             ← racine git (manage.py est ici)
├── CLAUDE.md                       ← règles et décisions de développement
├── ARCHITECTURE.md                 ← référence technique approfondie
├── manage.py
├── db.sqlite3                      ← base SQLite (dev uniquement, gitignored)
├── requirements.txt
├── FIDPHA001/                      ← package projet Django
│   ├── settings.py
│   ├── urls.py                     ← configuration URL racine
│   ├── wsgi.py
│   └── test_runner.py
├── fidpha/                         ← app principale (modèles, vues portail, services)
│   ├── models.py                   ← Account, UserProfile, Product, Contract, Contract_Product
│   ├── views.py                    ← vues portail (dashboard, contrats, ventes, pharmacie)
│   ├── services.py                 ← logique métier (get_active_contract, bulk_import_products, ...)
│   ├── adapters.py                 ← adaptateur Google OAuth
│   ├── urls.py                     ← routes /portal/*
│   ├── static/fidpha/css/
│   │   ├── portal.css              ← CSS partagé (portail + panneau de contrôle)
│   │   └── login.css
│   └── templates/fidpha/           ← templates HTML portail + templates emails
├── api/                            ← couche API REST
│   ├── models.py                   ← APIToken, APITokenUsageLog
│   ├── authentication.py           ← authentification par token SHA-256
│   ├── views.py                    ← endpoints /api/v1/
│   ├── portal_views.py             ← endpoints /api/portal/ (portail React pharmacie)
│   ├── staff_views.py              ← endpoints /api/staff/ (panneau React staff)
│   ├── serializers.py              ← sérialiseurs DRF pour les APIs portail et staff
│   ├── permissions.py              ← HasAPIToken, PortalSessionPermission, StaffSessionPermission
│   └── throttles.py                ← limitation de débit par token
├── sales/                          ← ingestion et stockage des ventes
│   ├── models.py                   ← SaleImport (brut), Sale (validé + points)
│   └── services.py                 ← submit_sales_batch() — point d'entrée unique d'ingestion
├── control/                        ← panneau de contrôle staff
│   ├── models.py                   ← SystemConfig (paramètres globaux)
│   ├── views.py                    ← toutes les vues du panneau (CRUD + revue des ventes)
│   ├── forms.py                    ← tous les formulaires et formsets
│   ├── decorators.py               ← @staff_required, @perm_required, @superuser_required
│   └── templates/control/          ← templates HTML du panneau de contrôle
├── locale/fr/LC_MESSAGES/          ← traductions françaises (.po source + .mo compilé)
├── static/                         ← statiques globaux (admin.css, JS admin)
├── templates/
│   ├── registration/               ← templates réinitialisation mot de passe
│   └── react/                      ← templates shell SPA (index.html, staff_index.html)
└── frontend/                       ← SPA React (branche feature/react-ui uniquement)
    ├── src/
    │   ├── api/client.js           ← wrapper fetch (session + CSRF)
    │   ├── components/Layout.jsx
    │   └── pages/                  ← Dashboard, Contracts, Points, Pharmacy
    ├── vite.config.js
    └── package.json
```

---

*Documentation WinInPharma — Mai 2026*
