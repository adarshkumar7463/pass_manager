# 🎫 PassManager — Ultimate Digital Pass Management System

[![Django](https://img.shields.io/badge/Django-4.2+-092e20?style=for-the-badge&logo=django&logoColor=white)](https://www.djangoproject.com/)
[![Python](https://img.shields.io/badge/Python-3.10+-3776ab?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Railway](https://img.shields.io/badge/Railway-Deploy-000000?style=for-the-badge&logo=railway&logoColor=white)](https://railway.app/)

**PassManager** is a professional, high-performance Django-based solution for generating, managing, and validating digital entry passes. Designed with a mobile-first approach, it features a premium UI, robust multi-location support, and real-time QR code validation.

---

## ✨ Key Features

- 🏢 **Multi-Location Support**: Manage multiple venues or gates with unique ID prefixes (e.g., `A-001`, `B-001`).
- 🎫 **Dynamic Pass Generation**: Users can generate passes by scanning a master QR code at the entrance.
- 🔍 **Real-Time QR Validation**: Built-in scanner for administrators to validate passes instantly via mobile camera or ID lookup.
- 📱 **Premium Mobile UI**: Stunning, responsive design with landscape-optimized pass cards and smooth animations.
- 🛠️ **Powerful Admin Dashboard**: Complete control over locations, templates, administrators, and real-time analytics.
- 💳 **Payment Tracking**: Record and track payments for each pass issued.
- 🛡️ **Rate Limiting**: Built-in protection against automated form submissions.
- 🖨️ **Export & Download**: High-quality pass rendering with "Download as Image" functionality.

---

## 🛠️ Tech Stack

- **Backend**: Django 4.2+, Python 3.10+
- **Database**: PostgreSQL (Production), SQLite (Development)
- **Frontend**: Vanilla HTML5, CSS3 (Modern Flex/Grid), Javascript (ES6+)
- **Security**: WhiteNoise (Static files), Rate-limiting middleware
- **Tools**: Pillow (Image processing), qrcode (QR Generation), ReportLab (PDF processing)

---

## 🚀 Quick Start

### 1. Prerequisites
- Python 3.10 or higher
- Git

### 2. Installation
```bash
# Clone the repository
git clone https://github.com/yourusername/passmanager.git
cd passmanager

# Create and activate virtual environment
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configuration
Copy the `.env.example` file to `.env` and configure your settings:
```bash
cp .env.example .env
```

| Variable | Description | Default |
|----------|-------------|---------|
| `DEBUG` | Set to `True` for development | `True` |
| `SECRET_KEY` | Django secret key | (Generated) |
| `SITE_URL` | Base URL for QR codes | `http://localhost:8000` |

### 4. Database & Admin Setup
```bash
# Run migrations
python manage.py migrate

# Initialize demo data (Creates admin user: admin / admin123)
python manage.py setup_demo
```

### 5. Run Server
```bash
python manage.py runserver
```
Visit `http://localhost:8000/admin-panel/login/` to get started.

---

## 📱 User Workflow

1. **Admin** creates a **Location** (e.g., "Main Gate").
2. **Admin** creates a **Pass Template** (Price, Discount, etc.).
3. **Admin** prints/shares the generated **Template QR**.
4. **Visitor** scans the QR → Fills details → Generates their **Unique Pass**.
5. **Visitor** presents the pass at the counter.
6. **Counter Admin** scans the pass → Validates status → Marks as **Used**.

---

## 🌐 Deployment

This project is optimized for easy deployment on **Railway** or **Render**.

- **Railway**: Auto-detects `Procfile` and PostgreSQL.
- **Render**: Uses `render.yaml` for blueprint deployment.

For detailed deployment instructions, see [DEPLOYMENT.md](DEPLOYMENT.md).

---

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

---

<p align="center">Made with ❤️ for seamless event management.</p>
