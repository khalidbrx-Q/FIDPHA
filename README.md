[English](#english) | [Français](#français)

---

<a name="english"></a>

# FIDPHA — Pharmacy Management System

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Environment Setup](#2-environment-setup)
3. [Django Project Setup](#3-django-project-setup)
4. [Database & Models](#4-database--models)
5. [Admin Panel](#5-admin-panel)
6. [Authentication System](#6-authentication-system)
7. [Pharmacy Portal](#7-pharmacy-portal)
8. [API](#8-api)
9. [Deployment](#9-deployment)
10. [Project Structure](#10-project-structure)

---

## 1. Project Overview

FIDPHA is a pharmacy management web application built with Django. It allows administrators to manage pharmacy accounts, contracts, and products through a polished admin interface, while providing pharmacy users with a dedicated portal to view their account information and contracts.

### Key Features

- Custom Django admin with Unfold theme
- Role-based access (superuser, staff, pharmacy users)
- Google OAuth login
- Email verification system
- Password reset via email
- Pharmacy portal dashboard with dark/light mode
- REST-ready API with token authentication
- Deployed on PythonAnywhere via GitHub

### Tech Stack

| Component | Technology |
|-----------|------------|
| Backend | Python 3.12, Django 5.2 |
| Admin Theme | django-unfold 0.87.0 |
| Authentication | django-allauth |
| Database | SQLite (development), upgradeable to MySQL |
| Deployment | PythonAnywhere + GitHub |

### Live Demo

🌐 [khalidbrx.pythonanywhere.com](https://khalidbrx.pythonanywhere.com)

---

## 2. Environment Setup

### 2.1 Install Python

Download and install Python 3.12 from [python.org](https://www.python.org/downloads/).

Verify installation:
```bash
python --version
# Python 3.12.x
```

### 2.2 Install PyCharm

Download PyCharm Community Edition from [jetbrains.com/pycharm](https://www.jetbrains.com/pycharm/).

### 2.3 Create Project Directory

```bash
mkdir FIDPHA001
cd FIDPHA001
```

### 2.4 Create Virtual Environment

```bash
python -m venv .venv
```

Activate it:

**Windows:**
```bash
.venv\Scripts\activate
```

**Mac/Linux:**
```bash
source .venv/bin/activate
```

### 2.5 Install Django and Required Packages

```bash
pip install django
pip install django-unfold
pip install django-allauth
pip install requests
pip install PyJWT
pip install cryptography
```

---

## 3. Django Project Setup

### 3.1 Create Django Project

```bash
django-admin startproject FIDPHA001 .
```

### 3.2 Create Django App

```bash
python manage.py startapp fidpha
```

### 3.3 Register App in settings.py

```python
INSTALLED_APPS = [
    "unfold",
    "unfold.contrib.filters",
    "unfold.contrib.forms",
    "fidpha.apps.FidphaConfig",
    "django.contrib.admin",
    # ... other apps
]
```

### 3.4 Configure Timezone

```python
TIME_ZONE = 'Africa/Casablanca'
USE_TZ = True
```

### 3.5 Run Initial Migrations and Create Superuser

```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Visit `http://127.0.0.1:8000` in your browser.

---

## 4. Database & Models

### 4.1 Models Overview

| Model | Description |
|-------|-------------|
| Account | Represents a pharmacy with contact info and portal access |
| UserProfile | Links a Django User to an Account with email verification |
| Product | A pharmaceutical product with internal code and designation |
| Contract | A time-bound contract between FIDPHA and a pharmacy |
| Contract_Product | Junction table linking products to contracts |

### 4.2 Relations

- **Account → Contract**: OneToMany (one account, many contracts)
- **Account → User**: OneToMany via UserProfile (one account, many users)
- **Contract → Product**: ManyToMany via Contract_Product
- `Contract_Product` carries an `external_designation` attribute

### 4.3 Business Rules

| Rule | Description |
|------|-------------|
| 1 | One account can have only one active contract at a time |
| 2 | Cannot deactivate a product linked to an active contract |
| 3 | Cannot deactivate an account with active contracts |
| 4 | Only users with pharmacy_portal=True can access the portal |
| 5 | Contract start_date must be <= end_date |
| 6 | external_designation maps internal products to pharmacy naming |

### 4.4 models.py

```python
from django.db import models
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User


class Account(models.Model):
    STATUS_CHOICES = [("active", "Active"), ("inactive", "Inactive")]
    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    location = models.TextField()
    phone = models.CharField(max_length=50)
    email = models.EmailField()
    pharmacy_portal = models.BooleanField(default=False)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)

    class Meta:
        db_table = "Account"

    def __str__(self):
        return f"[{self.code}] {self.name} - {self.city}"

    def clean(self):
        if self.status == "inactive" and self.pk:
            if self.contracts.filter(status="active").exists():
                raise ValidationError(
                    "Cannot deactivate this account because it has active contracts."
                )


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name="users")
    email_verified = models.BooleanField(default=False)
    verification_token = models.CharField(max_length=64, blank=True, null=True)
    token_created_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = "UserProfile"

    def __str__(self):
        return f"{self.user.username} → {self.account.name}"


class Product(models.Model):
    STATUS_CHOICES = [("active", "Active"), ("inactive", "Inactive")]
    code = models.CharField(max_length=50, unique=True)
    designation = models.CharField(max_length=255)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)

    class Meta:
        db_table = "Product"

    def __str__(self):
        return self.designation

    def clean(self):
        if self.status == "inactive" and self.pk:
            if Contract_Product.objects.filter(
                product=self, contract__status="active"
            ).exists():
                raise ValidationError(
                    "Cannot deactivate this product because it is in active contracts."
                )


class Contract(models.Model):
    STATUS_CHOICES = [("active", "Active"), ("inactive", "Inactive")]
    title = models.CharField(max_length=255)
    designation = models.TextField()
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name="contracts")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)
    products = models.ManyToManyField(Product, through="Contract_Product", related_name="contracts")

    class Meta:
        db_table = "Contract"

    def __str__(self):
        return self.title

    def clean(self):
        if self.start_date and self.end_date:
            if self.start_date > self.end_date:
                raise ValidationError("Start date must be before or equal to end date.")
        if self.status == "active" and self.account_id:
            active = Contract.objects.filter(account=self.account, status="active")
            if self.pk:
                active = active.exclude(pk=self.pk)
            if active.exists():
                raise ValidationError("This account already has an active contract.")


class Contract_Product(models.Model):
    contract = models.ForeignKey(Contract, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    external_designation = models.CharField(max_length=255)

    class Meta:
        db_table = "Contract_Product"
        unique_together = ("contract", "product")

    def __str__(self):
        return f"{self.contract} - {self.product}"
```

### 4.5 Run Migrations

```bash
python manage.py makemigrations
python manage.py migrate
```

---

## 5. Admin Panel

### 5.1 Unfold Theme Setup

Add to `INSTALLED_APPS` before `django.contrib.admin`:

```python
INSTALLED_APPS = [
    "unfold",
    "unfold.contrib.filters",
    "unfold.contrib.forms",
    "fidpha.apps.FidphaConfig",
    "django.contrib.admin",
]
```

Add Unfold configuration to `settings.py`:

```python
from django.templatetags.static import static
from django.urls import reverse_lazy

UNFOLD = {
    "SITE_TITLE": "FIDPHA Admin",
    "SITE_HEADER": "FIDPHA",
    "COLORS": {
        "primary": {
            "600": "27 103 155",
        },
    },
    "SIDEBAR": {
        "show_search": True,
        "navigation": [
            {
                "title": "FIDPHA",
                "icon": "local_pharmacy",
                "items": [
                    {
                        "title": "Accounts",
                        "icon": "store",
                        "link": reverse_lazy("admin:fidpha_account_changelist"),
                        "badge": "fidpha.utils.accounts_badge",
                    },
                ],
            },
        ],
    },
}
```

### 5.2 Key Admin Enhancements

| Feature | Description |
|---------|-------------|
| Auto-generate codes | Generate Account codes with one click via JS button |
| Inline contracts | Scrollable contract list inside Account detail page |
| Inline users | Only shows available non-staff users in Account page |
| Account details | Full account info shown inside User and Contract pages |
| Product counter | Number of products shown per contract in list view |
| Sidebar badges | Shows active/total counts for Accounts, Contracts, Products |
| Password strength | Live strength indicator when creating/changing passwords |
| Staff toggle | Profile inline hides automatically for staff users |
| Email status | Verification badge shown next to email field in User page |

### 5.3 utils.py (Sidebar Badges)

```python
def accounts_badge(request):
    from fidpha.models import Account
    active = Account.objects.filter(status='active').count()
    total = Account.objects.count()
    return f"{active}/{total}"

def contracts_badge(request):
    from fidpha.models import Contract
    active = Contract.objects.filter(status='active').count()
    total = Contract.objects.count()
    return f"{active}/{total}"

def products_badge(request):
    from fidpha.models import Product
    active = Product.objects.filter(status='active').count()
    total = Product.objects.count()
    return f"{active}/{total}"

def users_badge(request):
    from django.contrib.auth.models import User
    return User.objects.count()
```

---

## 6. Authentication System

### 6.1 Login Flow

```
User visits / → redirected to /portal/login/
↓
Login page (username + password OR Google)
↓
Staff user → /admin/
Non-staff user → check pharmacy_portal → /portal/dashboard/
```

### 6.2 Settings for Allauth

```python
INSTALLED_APPS += [
    "django.contrib.sites",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
]

SITE_ID = 1
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]
SOCIALACCOUNT_AUTO_SIGNUP = False
SOCIALACCOUNT_ADAPTER = "fidpha.adapters.FIDPHASocialAccountAdapter"
ACCOUNT_ADAPTER = "fidpha.adapters.FIDPHAAccountAdapter"
```

### 6.3 Google OAuth Setup

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create a new project
3. Go to **APIs & Services** → **OAuth consent screen** → External
4. Go to **Credentials** → **Create OAuth Client ID** → Web Application
5. Add authorized origins: `http://127.0.0.1:8000`
6. Add redirect URI: `http://127.0.0.1:8000/auth/google/login/callback/`
7. In Django admin → **Social Applications** → Add Google credentials
8. In Django admin → **Sites** → set domain to `127.0.0.1:8000`

### 6.4 Email Configuration (Gmail SMTP)

```python
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = 'your_email@gmail.com'
EMAIL_HOST_PASSWORD = 'your_app_password'
```

> To get an app password: Google Account → Security → 2-Step Verification → App Passwords

### 6.5 Email Verification Flow

```
New user logs in for first time
↓
Redirected to /portal/setup-profile/
↓
User enters email (+ optional name, password)
↓
Verification email sent with token link (expires in 24h)
↓
User clicks link → email_verified = True
↓
User can now access dashboard and use Google login
```

### 6.6 Password Reset Flow

```
User clicks "Forgot password?" on login page
↓
Enters email → system validates email exists
↓
Reset email sent with secure token link (expires in 24h)
↓
User clicks link → enters new password
↓
Password strength enforced (8+ chars, uppercase, number, special char)
↓
Redirected to login page
```

### 6.7 urls.py

```python
urlpatterns = [
    path("admin/login/", RedirectView.as_view(url="/portal/login/")),
    path("admin/logout/", fidpha_views.custom_logout),
    path("admin/", admin.site.urls),
    path("accounts/password_reset/", CustomPasswordResetView.as_view()),
    path("accounts/reset/<uidb64>/<token>/", CustomPasswordResetConfirmView.as_view()),
    path("accounts/", include("django.contrib.auth.urls")),
    path("portal/", include("fidpha.urls")),
    path("auth/", include("allauth.urls")),
    path("", lambda request: redirect("/portal/login/")),
]
```

---

## 7. Pharmacy Portal

### 7.1 Portal URLs

```python
# fidpha/urls.py
urlpatterns = [
    path("login/", views.custom_login, name="login"),
    path("dashboard/", views.portal_dashboard, name="dashboard"),
    path("setup-profile/", views.setup_profile, name="setup_profile"),
    path("verify-pending/", views.verify_pending, name="verify_pending"),
    path("verify-email/<str:token>/", views.verify_email, name="verify_email"),
    path("profile/", views.portal_profile, name="profile"),
    path("profile/password/", views.portal_profile_password, name="profile_password"),
    path("logout/", views.custom_logout, name="logout"),
]
```

### 7.2 Dashboard Features

- Pharmacy information (name, city, phone, email, status)
- Active and total contracts count
- All linked contracts with products table
- Email verification warning banner (if not verified)
- Dark/light mode toggle
- Collapsible sidebar with profile link

### 7.3 Profile Page Features

- View username (read-only, cannot be changed)
- Edit first name, last name, email
- Email verification status badge
- Change password (requires current password + new + confirmation)
- Password strength indicator with live checklist
- Linked account information

### 7.4 Portal Templates

| Template | Purpose |
|----------|---------|
| base.html | Sidebar, topbar, theme toggle — extended by all portal pages |
| dashboard.html | Pharmacy info, contracts, and product tables |
| profile.html | User profile editor with password change |
| login.html | Login page with Google OAuth button |
| setup_profile.html | First-time email and profile setup |
| verify_pending.html | Waiting for email verification confirmation |

---

## 8. API

### 8.1 Setup

```bash
pip install djangorestframework
```

```python
INSTALLED_APPS += ["rest_framework", "rest_framework.authtoken"]

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
}
```

### 8.2 Active Contract Endpoint

**Request:**
```
GET /api/contract/?accountId=1
Authorization: Token your_token_here
```

**Success Response (200):**
```json
{
    "contract": {
        "id": 1,
        "start_date": "2025-01-01 00:00",
        "end_date": "2025-12-31 00:00",
        "products": [
            {
                "product_id": 1,
                "internal_code": "PROD001",
                "external_designation": "MED_X"
            }
        ]
    }
}
```

**Error Response:**
```json
{
    "error": {
        "code": "CONTRACT_NOT_FOUND",
        "message": "No active contract found for account 1",
        "timestamp": "2026-01-01T00:00:00Z"
    }
}
```

### 8.3 HTTP Status Codes

| Code | Meaning |
|------|---------|
| 200 | Active contract found successfully |
| 400 | Missing or invalid accountId parameter |
| 401 | Missing or invalid authentication token |
| 403 | Valid token but insufficient permissions |
| 404 | No active contract found for this account |
| 500 | Unexpected server error |

### 8.4 Generate Token

Go to `/admin/` → Users → select user → Actions → **Generate API token**

---

## 9. Deployment

### 9.1 Prepare for Deployment

Update `settings.py`:

```python
DEBUG = False
ALLOWED_HOSTS = ['*', 'yourusername.pythonanywhere.com']
STATIC_ROOT = BASE_DIR / "staticfiles"
```

### 9.2 Create .gitignore

```
__pycache__/
*.py[cod]
.venv/
db.sqlite3
staticfiles/
*.log
.idea/
.env
```

### 9.3 Generate requirements.txt

```bash
pip freeze > requirements.txt
```

### 9.4 Push to GitHub

```bash
git init
git add .
git commit -m "initial commit"
git remote add origin https://github.com/yourusername/FIDPHA.git
git push -u origin main
```

### 9.5 Deploy on PythonAnywhere

**Step 1 — Clone repository:**
```bash
git clone https://github.com/yourusername/FIDPHA.git
```

**Step 2 — Create virtual environment:**
```bash
mkvirtualenv fidpha --python=python3.12
```

**Step 3 — Install dependencies:**
```bash
cd FIDPHA
pip install -r requirements.txt
```

**Step 4 — Set up database and static files:**
```bash
python manage.py migrate
python manage.py collectstatic
python manage.py createsuperuser
```

**Step 5 — Configure Web App on PythonAnywhere dashboard:**

Go to **Web** tab → **Add new web app** → Manual configuration → Python 3.12

Set the WSGI file content:
```python
import sys, os

path = '/home/yourusername/FIDPHA'
if path not in sys.path:
    sys.path.append(path)

os.environ['DJANGO_SETTINGS_MODULE'] = 'FIDPHA001.settings'

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
```

Set virtualenv to: `/home/yourusername/.virtualenvs/fidpha`

Set static files:

| URL | Directory |
|-----|-----------|
| `/static/` | `/home/yourusername/FIDPHA/staticfiles` |

**Step 6 — Click Reload**

### 9.6 Update After Changes

On local machine:
```bash
git add .
git commit -m "your message"
git push
```

On PythonAnywhere:
```bash
cd FIDPHA
git pull
python manage.py migrate        # only if models changed
python manage.py collectstatic  # only if static files changed
```

Then click **Reload** on the Web tab.

### 9.7 Configure Google OAuth for Production

In Google Cloud Console add:
- Authorized origins: `https://yourusername.pythonanywhere.com`
- Redirect URI: `https://yourusername.pythonanywhere.com/auth/google/login/callback/`

In Django admin → **Sites** → change domain to `yourusername.pythonanywhere.com`

In Django admin → **Social Applications** → add a new Google app with your Client ID and Secret.

---

## 10. Project Structure

```
FIDPHA001/                          ← Project root
├── .gitignore
├── manage.py
├── requirements.txt
├── static/                         ← Global static files
│   ├── admin.css                   ← Custom admin CSS
│   └── admin/
│       ├── account_form.js         ← Admin JS (generate code button)
│       └── user_form.js            ← Admin JS (password strength, staff toggle)
├── templates/                      ← Global templates
│   └── registration/               ← Password reset templates
├── FIDPHA001/                      ← Django project settings
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
└── fidpha/                         ← Main Django app
    ├── migrations/
    ├── static/fidpha/
    │   ├── css/
    │   │   ├── portal.css          ← Portal styles
    │   │   └── login.css           ← Login page styles
    │   └── js/
    │       └── portal.js           ← Portal JavaScript
    ├── templates/fidpha/
    │   ├── base.html               ← Base portal template
    │   ├── dashboard.html          ← Pharmacy dashboard
    │   ├── profile.html            ← User profile editor
    │   ├── login.html              ← Login page
    │   ├── setup_profile.html      ← First-time profile setup
    │   └── verify_pending.html     ← Email verification pending
    ├── adapters.py                 ← Allauth social account adapters
    ├── admin.py                    ← Admin panel configuration
    ├── apps.py
    ├── models.py                   ← Database models
    ├── urls.py                     ← Portal URL routes
    ├── utils.py                    ← Sidebar badge helpers
    └── views.py                    ← Portal views and auth logic
```

---

*FIDPHA Documentation — April 2026*

---
---

<a name="français"></a>

# FIDPHA — Système de Gestion des Pharmacies

## Table des Matières

1. [Aperçu du Projet](#1-aperçu-du-projet)
2. [Configuration de l'Environnement](#2-configuration-de-lenvironnement)
3. [Configuration du Projet Django](#3-configuration-du-projet-django)
4. [Base de Données & Modèles](#4-base-de-données--modèles)
5. [Panneau d'Administration](#5-panneau-dadministration)
6. [Système d'Authentification](#6-système-dauthentification)
7. [Portail Pharmacie](#7-portail-pharmacie)
8. [API](#8-api)
9. [Déploiement](#9-déploiement)
10. [Structure du Projet](#10-structure-du-projet)

---

## 1. Aperçu du Projet

FIDPHA est une application web de gestion des pharmacies construite avec Django. Elle permet aux administrateurs de gérer les comptes pharmacies, les contrats et les produits via une interface d'administration soignée, tout en offrant aux utilisateurs pharmacie un portail dédié pour consulter leurs informations et leurs contrats.

### Fonctionnalités Clés

- Interface d'administration Django personnalisée avec le thème Unfold
- Accès basé sur les rôles (superutilisateur, staff, utilisateurs pharmacie)
- Connexion Google OAuth
- Système de vérification d'email
- Réinitialisation du mot de passe par email
- Tableau de bord du portail pharmacie avec mode sombre/clair
- API REST avec authentification par token
- Déployé sur PythonAnywhere via GitHub

### Stack Technique

| Composant | Technologie |
|-----------|-------------|
| Backend | Python 3.12, Django 5.2 |
| Thème Admin | django-unfold 0.87.0 |
| Authentification | django-allauth |
| Base de données | SQLite (développement), évolutif vers MySQL |
| Déploiement | PythonAnywhere + GitHub |

### Démo en Ligne

🌐 [khalidbrx.pythonanywhere.com](https://khalidbrx.pythonanywhere.com)

---

## 2. Configuration de l'Environnement

### 2.1 Installer Python

Téléchargez et installez Python 3.12 depuis [python.org](https://www.python.org/downloads/).

Vérifiez l'installation :
```bash
python --version
# Python 3.12.x
```

### 2.2 Installer PyCharm

Téléchargez PyCharm Community Edition depuis [jetbrains.com/pycharm](https://www.jetbrains.com/pycharm/).

### 2.3 Créer le Répertoire du Projet

```bash
mkdir FIDPHA001
cd FIDPHA001
```

### 2.4 Créer un Environnement Virtuel

```bash
python -m venv .venv
```

Activez-le :

**Windows :**
```bash
.venv\Scripts\activate
```

**Mac/Linux :**
```bash
source .venv/bin/activate
```

### 2.5 Installer Django et les Packages Requis

```bash
pip install django
pip install django-unfold
pip install django-allauth
pip install requests
pip install PyJWT
pip install cryptography
```

---

## 3. Configuration du Projet Django

### 3.1 Créer le Projet Django

```bash
django-admin startproject FIDPHA001 .
```

### 3.2 Créer l'Application Django

```bash
python manage.py startapp fidpha
```

### 3.3 Enregistrer l'Application dans settings.py

```python
INSTALLED_APPS = [
    "unfold",
    "unfold.contrib.filters",
    "unfold.contrib.forms",
    "fidpha.apps.FidphaConfig",
    "django.contrib.admin",
    # ... autres apps
]
```

### 3.4 Configurer le Fuseau Horaire

```python
TIME_ZONE = 'Africa/Casablanca'
USE_TZ = True
```

### 3.5 Lancer les Migrations Initiales et Créer un Superutilisateur

```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Visitez `http://127.0.0.1:8000` dans votre navigateur.

---

## 4. Base de Données & Modèles

### 4.1 Aperçu des Modèles

| Modèle | Description |
|--------|-------------|
| Account | Représente une pharmacie avec ses informations de contact |
| UserProfile | Lie un Utilisateur Django à un Compte avec vérification email |
| Product | Un produit pharmaceutique avec code interne et désignation |
| Contract | Un contrat limité dans le temps entre FIDPHA et une pharmacie |
| Contract_Product | Table de jonction liant les produits aux contrats |

### 4.2 Relations

- **Account → Contract** : OneToMany (un compte, plusieurs contrats)
- **Account → User** : OneToMany via UserProfile (un compte, plusieurs utilisateurs)
- **Contract → Product** : ManyToMany via Contract_Product
- `Contract_Product` porte un attribut `external_designation`

### 4.3 Règles Métier

| Règle | Description |
|-------|-------------|
| 1 | Un compte ne peut avoir qu'un seul contrat actif à la fois |
| 2 | Impossible de désactiver un produit lié à un contrat actif |
| 3 | Impossible de désactiver un compte avec des contrats actifs |
| 4 | Seuls les utilisateurs avec pharmacy_portal=True peuvent accéder au portail |
| 5 | La date de début du contrat doit être <= à la date de fin |
| 6 | external_designation mappe les produits internes au nommage de la pharmacie |

### 4.4 models.py

```python
from django.db import models
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User


class Account(models.Model):
    STATUS_CHOICES = [("active", "Actif"), ("inactive", "Inactif")]
    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    location = models.TextField()
    phone = models.CharField(max_length=50)
    email = models.EmailField()
    pharmacy_portal = models.BooleanField(default=False)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)

    class Meta:
        db_table = "Account"

    def __str__(self):
        return f"[{self.code}] {self.name} - {self.city}"

    def clean(self):
        # Règle 3 : impossible de désactiver un compte avec des contrats actifs
        if self.status == "inactive" and self.pk:
            if self.contracts.filter(status="active").exists():
                raise ValidationError(
                    "Impossible de désactiver ce compte car il a des contrats actifs."
                )


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name="users")
    email_verified = models.BooleanField(default=False)
    verification_token = models.CharField(max_length=64, blank=True, null=True)
    token_created_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = "UserProfile"

    def __str__(self):
        return f"{self.user.username} → {self.account.name}"


class Product(models.Model):
    STATUS_CHOICES = [("active", "Actif"), ("inactive", "Inactif")]
    code = models.CharField(max_length=50, unique=True)
    designation = models.CharField(max_length=255)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)

    class Meta:
        db_table = "Product"

    def __str__(self):
        return self.designation

    def clean(self):
        # Règle 2 : impossible de désactiver un produit dans un contrat actif
        if self.status == "inactive" and self.pk:
            if Contract_Product.objects.filter(
                product=self, contract__status="active"
            ).exists():
                raise ValidationError(
                    "Impossible de désactiver ce produit car il est dans des contrats actifs."
                )


class Contract(models.Model):
    STATUS_CHOICES = [("active", "Actif"), ("inactive", "Inactif")]
    title = models.CharField(max_length=255)
    designation = models.TextField()
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name="contracts")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)
    products = models.ManyToManyField(Product, through="Contract_Product", related_name="contracts")

    class Meta:
        db_table = "Contract"

    def __str__(self):
        return self.title

    def clean(self):
        # Règle 5 : date début <= date fin
        if self.start_date and self.end_date:
            if self.start_date > self.end_date:
                raise ValidationError("La date de début doit être avant ou égale à la date de fin.")
        # Règle 1 : un seul contrat actif par compte
        if self.status == "active" and self.account_id:
            active = Contract.objects.filter(account=self.account, status="active")
            if self.pk:
                active = active.exclude(pk=self.pk)
            if active.exists():
                raise ValidationError("Ce compte a déjà un contrat actif.")


class Contract_Product(models.Model):
    contract = models.ForeignKey(Contract, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    external_designation = models.CharField(max_length=255)

    class Meta:
        db_table = "Contract_Product"
        unique_together = ("contract", "product")

    def __str__(self):
        return f"{self.contract} - {self.product}"
```

### 4.5 Lancer les Migrations

```bash
python manage.py makemigrations
python manage.py migrate
```

---

## 5. Panneau d'Administration

### 5.1 Configuration du Thème Unfold

Ajoutez à `INSTALLED_APPS` avant `django.contrib.admin` :

```python
INSTALLED_APPS = [
    "unfold",
    "unfold.contrib.filters",
    "unfold.contrib.forms",
    "fidpha.apps.FidphaConfig",
    "django.contrib.admin",
]
```

### 5.2 Améliorations Clés de l'Admin

| Fonctionnalité | Description |
|----------------|-------------|
| Génération automatique de codes | Génère des codes Compte en un clic via un bouton JS |
| Contrats inline | Liste scrollable de contrats dans la page de détail du Compte |
| Utilisateurs inline | Affiche uniquement les utilisateurs non-staff disponibles |
| Détails du compte | Informations complètes du compte dans les pages Utilisateur et Contrat |
| Compteur de produits | Nombre de produits affiché par contrat dans la liste |
| Badges de la barre latérale | Affiche les comptages actif/total pour Comptes, Contrats, Produits |
| Force du mot de passe | Indicateur en temps réel lors de la création/modification de mots de passe |
| Bascule staff | L'inline du profil se cache automatiquement pour les utilisateurs staff |
| Statut email | Badge de vérification affiché à côté du champ email dans la page Utilisateur |

---

## 6. Système d'Authentification

### 6.1 Flux de Connexion

```
L'utilisateur visite / → redirigé vers /portal/login/
↓
Page de connexion (nom d'utilisateur + mot de passe OU Google)
↓
Utilisateur staff → /admin/
Utilisateur non-staff → vérification pharmacy_portal → /portal/dashboard/
```

### 6.2 Configuration d'Allauth

```python
INSTALLED_APPS += [
    "django.contrib.sites",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
]

SITE_ID = 1
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]
SOCIALACCOUNT_AUTO_SIGNUP = False
SOCIALACCOUNT_ADAPTER = "fidpha.adapters.FIDPHASocialAccountAdapter"
ACCOUNT_ADAPTER = "fidpha.adapters.FIDPHAAccountAdapter"
```

### 6.3 Configuration Google OAuth

1. Aller sur [console.cloud.google.com](https://console.cloud.google.com)
2. Créer un nouveau projet
3. Aller dans **APIs & Services** → **Écran de consentement OAuth** → Externe
4. Aller dans **Identifiants** → **Créer un identifiant OAuth** → Application Web
5. Ajouter les origines autorisées : `http://127.0.0.1:8000`
6. Ajouter l'URI de redirection : `http://127.0.0.1:8000/auth/google/login/callback/`
7. Dans l'admin Django → **Applications Sociales** → Ajouter les identifiants Google
8. Dans l'admin Django → **Sites** → Définir le domaine sur `127.0.0.1:8000`

### 6.4 Configuration Email (Gmail SMTP)

```python
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = 'votre_email@gmail.com'
EMAIL_HOST_PASSWORD = 'votre_mot_de_passe_application'
```

> Pour obtenir un mot de passe d'application : Compte Google → Sécurité → Validation en 2 étapes → Mots de passe des applications

### 6.5 Flux de Vérification Email

```
Nouvel utilisateur se connecte pour la première fois
↓
Redirigé vers /portal/setup-profile/
↓
L'utilisateur saisit son email (+ nom/prénom et mot de passe optionnels)
↓
Email de vérification envoyé avec lien token (expire en 24h)
↓
L'utilisateur clique le lien → email_verified = True
↓
L'utilisateur peut accéder au tableau de bord et utiliser Google login
```

### 6.6 Flux de Réinitialisation du Mot de Passe

```
L'utilisateur clique "Mot de passe oublié ?" sur la page de connexion
↓
Saisit son email → le système vérifie que l'email existe
↓
Email de réinitialisation envoyé avec lien sécurisé (expire en 24h)
↓
L'utilisateur clique le lien → saisit un nouveau mot de passe
↓
Force du mot de passe imposée (8+ caractères, majuscule, chiffre, caractère spécial)
↓
Redirigé vers la page de connexion
```

---

## 7. Portail Pharmacie

### 7.1 URLs du Portail

```python
# fidpha/urls.py
urlpatterns = [
    path("login/", views.custom_login, name="login"),
    path("dashboard/", views.portal_dashboard, name="dashboard"),
    path("setup-profile/", views.setup_profile, name="setup_profile"),
    path("verify-pending/", views.verify_pending, name="verify_pending"),
    path("verify-email/<str:token>/", views.verify_email, name="verify_email"),
    path("profile/", views.portal_profile, name="profile"),
    path("profile/password/", views.portal_profile_password, name="profile_password"),
    path("logout/", views.custom_logout, name="logout"),
]
```

### 7.2 Fonctionnalités du Tableau de Bord

- Informations pharmacie (nom, ville, téléphone, email, statut)
- Comptage des contrats actifs et total
- Tous les contrats liés avec tableau de produits
- Bannière d'avertissement de vérification email (si non vérifié)
- Bascule mode sombre/clair
- Barre latérale rétractable avec lien profil

### 7.3 Fonctionnalités de la Page Profil

- Voir le nom d'utilisateur (lecture seule, non modifiable)
- Modifier prénom, nom, email
- Badge de statut de vérification email
- Changer le mot de passe (requiert mot de passe actuel + nouveau + confirmation)
- Indicateur de force du mot de passe avec checklist en temps réel
- Informations du compte lié

### 7.4 Templates du Portail

| Template | Rôle |
|----------|------|
| base.html | Barre latérale, barre supérieure, bascule thème — étendu par toutes les pages |
| dashboard.html | Infos pharmacie, contrats et tableaux de produits |
| profile.html | Éditeur de profil utilisateur avec changement de mot de passe |
| login.html | Page de connexion avec bouton Google OAuth |
| setup_profile.html | Configuration du profil lors de la première connexion |
| verify_pending.html | En attente de confirmation de vérification email |

---

## 8. API

### 8.1 Configuration

```bash
pip install djangorestframework
```

```python
INSTALLED_APPS += ["rest_framework", "rest_framework.authtoken"]

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
}
```

### 8.2 Endpoint Contrat Actif

**Requête :**
```
GET /api/contract/?accountId=1
Authorization: Token votre_token_ici
```

**Réponse Succès (200) :**
```json
{
    "contract": {
        "id": 1,
        "start_date": "2025-01-01 00:00",
        "end_date": "2025-12-31 00:00",
        "products": [
            {
                "product_id": 1,
                "internal_code": "PROD001",
                "external_designation": "MED_X"
            }
        ]
    }
}
```

### 8.3 Codes HTTP

| Code | Signification |
|------|---------------|
| 200 | Contrat actif trouvé avec succès |
| 400 | accountId manquant ou invalide |
| 401 | Token d'authentification manquant ou invalide |
| 403 | Token valide mais permissions insuffisantes |
| 404 | Aucun contrat actif trouvé pour ce compte |
| 500 | Erreur interne du serveur |

### 8.4 Générer un Token

Aller dans `/admin/` → Utilisateurs → sélectionner un utilisateur → Actions → **Générer un token API**

---

## 9. Déploiement

### 9.1 Préparer le Déploiement

Mettre à jour `settings.py` :

```python
DEBUG = False
ALLOWED_HOSTS = ['*', 'votrenom.pythonanywhere.com']
STATIC_ROOT = BASE_DIR / "staticfiles"
```

### 9.2 Créer .gitignore

```
__pycache__/
*.py[cod]
.venv/
db.sqlite3
staticfiles/
*.log
.idea/
.env
```

### 9.3 Générer requirements.txt

```bash
pip freeze > requirements.txt
```

### 9.4 Pousser sur GitHub

```bash
git init
git add .
git commit -m "commit initial"
git remote add origin https://github.com/votrenom/FIDPHA.git
git push -u origin main
```

### 9.5 Déployer sur PythonAnywhere

**Étape 1 — Cloner le dépôt :**
```bash
git clone https://github.com/votrenom/FIDPHA.git
```

**Étape 2 — Créer l'environnement virtuel :**
```bash
mkvirtualenv fidpha --python=python3.12
```

**Étape 3 — Installer les dépendances :**
```bash
cd FIDPHA
pip install -r requirements.txt
```

**Étape 4 — Configurer la base de données et les fichiers statiques :**
```bash
python manage.py migrate
python manage.py collectstatic
python manage.py createsuperuser
```

**Étape 5 — Configurer l'application Web sur le tableau de bord PythonAnywhere :**

Aller dans l'onglet **Web** → **Ajouter une nouvelle application web** → Configuration manuelle → Python 3.12

Contenu du fichier WSGI :
```python
import sys, os

path = '/home/votrenom/FIDPHA'
if path not in sys.path:
    sys.path.append(path)

os.environ['DJANGO_SETTINGS_MODULE'] = 'FIDPHA001.settings'

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
```

Virtualenv : `/home/votrenom/.virtualenvs/fidpha`

Fichiers statiques :

| URL | Répertoire |
|-----|------------|
| `/static/` | `/home/votrenom/FIDPHA/staticfiles` |

**Étape 6 — Cliquer sur Reload**

### 9.6 Mettre à Jour Après des Modifications

Sur la machine locale :
```bash
git add .
git commit -m "description des modifications"
git push
```

Sur PythonAnywhere :
```bash
cd FIDPHA
git pull
python manage.py migrate        # uniquement si les modèles ont changé
python manage.py collectstatic  # uniquement si les fichiers statiques ont changé
```

Puis cliquer sur **Reload** dans l'onglet Web.

### 9.7 Configurer Google OAuth pour la Production

Dans Google Cloud Console ajouter :
- Origines autorisées : `https://votrenom.pythonanywhere.com`
- URI de redirection : `https://votrenom.pythonanywhere.com/auth/google/login/callback/`

Dans l'admin Django → **Sites** → changer le domaine en `votrenom.pythonanywhere.com`

Dans l'admin Django → **Applications Sociales** → ajouter une nouvelle app Google avec votre Client ID et Secret.

---

## 10. Structure du Projet

```
FIDPHA001/                          ← Racine du projet
├── .gitignore
├── manage.py
├── requirements.txt
├── static/                         ← Fichiers statiques globaux
│   ├── admin.css                   ← CSS admin personnalisé
│   └── admin/
│       ├── account_form.js         ← JS admin (bouton génération code)
│       └── user_form.js            ← JS admin (force mot de passe, bascule staff)
├── templates/                      ← Templates globaux
│   └── registration/               ← Templates réinitialisation mot de passe
├── FIDPHA001/                      ← Paramètres du projet Django
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
└── fidpha/                         ← Application Django principale
    ├── migrations/
    ├── static/fidpha/
    │   ├── css/
    │   │   ├── portal.css          ← Styles du portail
    │   │   └── login.css           ← Styles de la page de connexion
    │   └── js/
    │       └── portal.js           ← JavaScript du portail
    ├── templates/fidpha/
    │   ├── base.html               ← Template de base du portail
    │   ├── dashboard.html          ← Tableau de bord pharmacie
    │   ├── profile.html            ← Éditeur de profil utilisateur
    │   ├── login.html              ← Page de connexion
    │   ├── setup_profile.html      ← Configuration profil première connexion
    │   └── verify_pending.html     ← Vérification email en attente
    ├── adapters.py                 ← Adaptateurs allauth
    ├── admin.py                    ← Configuration du panneau d'administration
    ├── apps.py
    ├── models.py                   ← Modèles de base de données
    ├── urls.py                     ← Routes URL du portail
    ├── utils.py                    ← Fonctions helpers pour les badges
    └── views.py                    ← Vues du portail et logique d'authentification
```

---

*Documentation FIDPHA — Avril 2026*
