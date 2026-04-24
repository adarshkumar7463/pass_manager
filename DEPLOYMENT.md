# 🚀 PassManager — Full Deployment Guide

## Table of Contents
1. [Local Development Setup](#1-local-development-setup)
2. [Deploy to Railway (Recommended)](#2-deploy-to-railway)
3. [Deploy to Render](#3-deploy-to-render)
4. [Custom Domain Setup](#4-custom-domain)
5. [Environment Variables Reference](#5-environment-variables)
6. [Admin User Guide](#6-admin-user-guide)
7. [Architecture Overview](#7-architecture)

---

## 1. Local Development Setup

### Prerequisites
- Python 3.10+ installed
- Git installed

### Steps

```bash
# 1. Clone / unzip the project
cd passmanager

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate        # macOS/Linux
# OR
venv\Scripts\activate            # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy env file
cp .env.example .env
# Edit .env: set DEBUG=True, keep DATABASE_URL as sqlite

# 5. Run migrations
python manage.py migrate

# 6. Create admin + demo data (one command)
python manage.py setup_demo

# 7. Run development server
python manage.py runserver
```

**Access:**
- Admin Panel: http://localhost:8000/admin-panel/login/
- Default Login: `admin` / `admin123`
- Pass Generation (demo): http://localhost:8000/generate-pass/1/

---

## 2. Deploy to Railway

Railway gives you free PostgreSQL + free hosting tier. Recommended for beginners.

### Step-by-step

**A. Push your code to GitHub**
```bash
git init
git add .
git commit -m "Initial commit"
# Create a repo on github.com, then:
git remote add origin https://github.com/YOUR_USERNAME/passmanager.git
git push -u origin main
```

**B. Create Railway Project**
1. Go to https://railway.app → Sign up/login
2. Click **"New Project"** → **"Deploy from GitHub repo"**
3. Select your repo

**C. Add PostgreSQL**
1. In your Railway project → click **"+ New"** → **"Database"** → **"PostgreSQL"**
2. Railway auto-sets `DATABASE_URL` — no action needed

**D. Set Environment Variables**
In Railway → your service → **Variables** tab, add:

```
SECRET_KEY        = (generate: python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())")
DEBUG             = False
ALLOWED_HOSTS     = your-app.up.railway.app,yourdomain.com
SITE_URL          = https://your-app.up.railway.app
SECURE_SSL_REDIRECT = False
RATE_LIMIT_REQUESTS = 5
RATE_LIMIT_WINDOW   = 3600
```

> `DATABASE_URL` is set automatically by Railway when you link the PostgreSQL service.

**E. Deploy**
Railway auto-deploys on push. Watch logs in the **Deployments** tab.

**F. Run Setup Command (one-time)**
In Railway → your service → **Shell** tab:
```bash
python manage.py setup_demo --username=youradmin --password=yourpassword
```

---

## 3. Deploy to Render

**A. Create `render.yaml`** (already included — shown below for reference):

```yaml
services:
  - type: web
    name: passmanager
    env: python
    buildCommand: pip install -r requirements.txt && python manage.py collectstatic --noinput
    startCommand: gunicorn passmanager.wsgi --bind 0.0.0.0:$PORT
    envVars:
      - key: SECRET_KEY
        generateValue: true
      - key: DEBUG
        value: False
      - key: DATABASE_URL
        fromDatabase:
          name: passmanager-db
          property: connectionString

databases:
  - name: passmanager-db
    plan: free
```

**B. Steps**
1. Push code to GitHub
2. Go to https://render.com → New → Web Service → Connect GitHub repo
3. Add environment variables in Render dashboard
4. Deploy

---

## 4. Custom Domain

### Railway
1. Railway → Settings → Domains → Add Custom Domain
2. Add your domain (e.g. `passes.yoursite.com`)
3. Copy the CNAME value Railway gives you
4. In your DNS provider (Cloudflare, GoDaddy, etc.), add:
   - Type: `CNAME`
   - Name: `passes` (or `@` for root)
   - Value: (paste Railway's CNAME)
5. Update `ALLOWED_HOSTS` and `SITE_URL` environment variables to your domain
6. Set `SECURE_SSL_REDIRECT=True` (Railway handles SSL automatically)

### Render
Similar process — Render → Settings → Custom Domains → Add domain → update DNS.

---

## 5. Environment Variables Reference

| Variable | Required | Description | Example |
|---|---|---|---|
| `SECRET_KEY` | ✅ | Django secret key | `xK9#mP2...` |
| `DEBUG` | ✅ | False in production | `False` |
| `ALLOWED_HOSTS` | ✅ | Comma-separated hosts | `passes.mysite.com` |
| `DATABASE_URL` | ✅ Prod | PostgreSQL connection URL | `postgres://...` |
| `SITE_URL` | ✅ | Used in QR codes | `https://passes.mysite.com` |
| `RATE_LIMIT_REQUESTS` | Optional | Max form submissions per IP per window | `5` |
| `RATE_LIMIT_WINDOW` | Optional | Rate limit window in seconds | `3600` |
| `SECURE_SSL_REDIRECT` | Optional | Redirect HTTP → HTTPS | `True` |

---

## 6. Admin User Guide

### Workflow
```
Superadmin
    ↓ Creates Locations (e.g. "Main Gate" prefix A, "Zone B" prefix B)
    ↓ Creates Pass Templates per location (with discount, price, limit)
    ↓ QR Code auto-generated → share/print it at the venue entrance

Visitor
    ↓ Scans QR code → opens form on their phone
    ↓ Fills Name, Phone, Address → clicks "Generate My Pass"
    ↓ Gets unique Pass Card (e.g. A-001) on screen
    ↓ Shows pass at counter

Counter Admin
    ↓ Opens Admin Panel → Validate Pass
    ↓ Scans pass QR or types Pass ID (A-001)
    ↓ Sees: ✅ VALID or ❌ INVALID
    ↓ Clicks "Mark Payment Done" → pass status → USED
    ↓ Or clicks "Expire Pass" → pass status → EXPIRED
```

### Creating a New Location
1. Admin Panel → Locations → New Location
2. Fill: Name, Prefix (e.g. `A`), Description, Image
3. Save — prefix is permanent (used in all Pass IDs)

### Creating a Pass Template
1. Admin Panel → New Template
2. Select Location, enter name, price, discount
3. Set Access Limit (or leave blank for unlimited)
4. Submit → QR code is generated
5. Download QR → print it → stick at venue entrance

### Validating Passes
1. Admin Panel → Validate Pass
2. Option A: Type Pass ID (e.g. `A-001`) → Lookup
3. Option B: Click "Start Camera" → scan pass QR
4. Admin can see: Name, Phone, Status, Date
5. Click "Mark Payment Done" → records payment
6. Click "Expire Pass" → invalidates pass permanently

### Managing Admins (Superadmin only)
1. Admin Panel → Manage Admins → New Admin
2. Set username/password, assign locations
3. That admin can ONLY see templates/passes for their assigned locations

---

## 7. Architecture Overview

```
passmanager/
├── passmanager/              ← Django project config
│   ├── settings.py           ← All settings, env-based
│   └── urls.py               ← Root URL routing
│
├── apps/
│   ├── locations/            ← Location model + CRUD
│   │   ├── models.py         ← Location, AdminLocation
│   │   └── views.py          ← Create/edit locations
│   │
│   ├── passes/               ← Core pass system
│   │   ├── models.py         ← PassTemplate, Pass, PaymentRecord, Counter
│   │   ├── views.py          ← User flow + admin validation
│   │   ├── middleware.py     ← IP rate limiting
│   │   └── urls.py           ← All URL patterns
│   │
│   └── accounts/             ← Auth + user management
│       ├── views.py          ← Login, logout, user CRUD
│       └── urls.py
│
├── templates/
│   ├── base/                 ← base.html, admin_base.html
│   ├── admin_panel/          ← Dashboard, templates, validate, analytics
│   └── passes/               ← Public: generate_pass, view_pass
│
├── static/
│   ├── css/main.css          ← Complete design system
│   └── js/main.js            ← Sidebar, toast, scanner helpers
│
├── requirements.txt
├── Procfile                  ← For Railway/Render
└── .env.example
```

### Database Models

```
Location
  ├── name, slug, prefix (e.g. "A")
  ├── image, description, address
  └── AdminLocation (user ↔ location link)

PassTemplate
  ├── → Location
  ├── name, discount_percent, total_price
  ├── access_limit (nullable = unlimited)
  ├── is_active, qr_code (ImageField)
  └── generate_qr() method

LocationPassCounter
  └── → Location (one-to-one)
      Auto-increments: A-001, A-002, B-001…

Pass
  ├── → PassTemplate
  ├── unique_id (A-001), full_name, phone, address
  ├── status: ACTIVE | EXPIRED | USED
  └── pass_qr (individual QR for this pass)

PaymentRecord
  └── → Pass (one-to-one)
      amount_paid, payment_method, recorded_by
```

---

## Quick Start Checklist

- [ ] Clone/unzip project
- [ ] `pip install -r requirements.txt`
- [ ] `python manage.py migrate`
- [ ] `python manage.py setup_demo`
- [ ] Open http://localhost:8000/admin-panel/login/
- [ ] Login: admin / admin123
- [ ] Create a Location
- [ ] Create a Pass Template
- [ ] Copy the QR URL → open on phone → test form
- [ ] Go to Validate Pass → test validation
- [ ] Deploy to Railway/Render
- [ ] Set `SITE_URL` to production domain
- [ ] Run `setup_demo` on production with secure credentials
