<p align="center">
  <h1 align="center">CollabHub</h1>
  <p align="center">
    <strong>Enterprise Collaboration & Hierarchical Access Management Platform</strong>
  </p>
  <p align="center">
    <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python"></a>
    <a href="https://fastapi.tiangolo.com/"><img src="https://img.shields.io/badge/FastAPI-0.115-009688?style=flat-square&logo=fastapi&logoColor=white" alt="FastAPI"></a>
    <a href="https://www.sqlite.org/"><img src="https://img.shields.io/badge/SQLite-Database-003B57?style=flat-square&logo=sqlite&logoColor=white" alt="SQLite"></a>
    <a href="https://ai.google.dev/"><img src="https://img.shields.io/badge/Gemini-2.5--flash-4285F4?style=flat-square&logo=google&logoColor=white" alt="Gemini"></a>
    <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-yellow?style=flat-square" alt="License"></a>
  </p>
</p>

---

A full-stack enterprise collaboration platform with hierarchical role-based access control, AI-powered document intelligence, and comprehensive audit logging — built with FastAPI and server-rendered templates.

## What This App Does

CollabHub is an enterprise collaboration platform with hierarchical role-based access control designed for teams that need structured project management and document workflows. It supports project management, document upload with AI-powered summarization via Google Gemini, team member assignment, and comprehensive audit logging. Three roles — **Admin**, **Manager**, and **Member** — enforce granular permissions across all features, ensuring that sensitive actions are restricted to authorized personnel.

## Tech Stack

| Layer              | Technology                                                         |
| ------------------ | ------------------------------------------------------------------ |
| **Backend**        | Python 3.10+, FastAPI                                              |
| **Database**       | SQLite (single file, auto-created)                                 |
| **Frontend**       | Server-rendered HTML (Jinja2 templates), vanilla CSS, vanilla JavaScript |
| **Authentication** | JWT tokens in HttpOnly cookies, bcrypt password hashing            |
| **AI**             | Google Gemini (`gemini-2.5-flash`) via `google-genai` SDK          |
| **File Storage**   | SQLite BLOB (files stored in the database, no external storage needed) |

## Setup Instructions

```bash
# 1. Clone the repository
git clone https://github.com/yourusername/collabhub.git
cd collabhub

# 2. Create and activate a virtual environment
python -m venv venv
venv\Scripts\activate     # Windows
source venv/bin/activate  # macOS/Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment variables
cp .env.example .env
# Edit .env and set your GEMINI_API_KEY and a random SECRET_KEY

# 5. Seed the database with demo data
python seed.py

# 6. Start the development server
uvicorn app.main:app --reload

# 7. Open your browser
# Visit http://localhost:8000
```

> **Note**: No manual database setup is needed. SQLite tables are auto-created on first run.

## Deployment (Render)

Follow these steps to deploy CollabHub to [Render](https://render.com):

1. **Push your code** to a GitHub repository.

2. Go to [render.com](https://render.com) and create a **New Web Service**.

3. **Connect** your GitHub repository.

4. **Configure** the service:
   - **Build Command**: `pip install -r requirements.txt && python seed.py`
   - **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

5. Add **Environment Variables** in the Render dashboard:

   | Variable        | Value                                    |
   | --------------- | ---------------------------------------- |
   | `SECRET_KEY`    | A randomly generated 32+ character string |
   | `GEMINI_API_KEY`| Your Google Gemini API key               |
   | `DATABASE_URL`  | `sqlite:///./collabhub.db`               |
   | `MAX_FILE_SIZE` | `10485760`                               |

6. Click **Deploy** — your app will be live at `https://your-app.onrender.com`.

> **Note**: On Render's free tier, the filesystem is ephemeral. The SQLite database (and all uploaded documents stored as BLOBs within it) will be reset on each redeploy. The seed script runs during build, so demo data will always be available. For persistent storage, use Render's paid tier with a Persistent Disk.

## AI Feature — LLM Provider Disclosure

| Detail        | Description                                                                      |
| ------------- | -------------------------------------------------------------------------------- |
| **Provider**  | Google Gemini (Google AI Studio)                                                 |
| **Model**     | `gemini-2.5-flash`                                                               |
| **Setup**     | BYOK (Bring Your Own Key) — set the `GEMINI_API_KEY` environment variable        |
| **Get a key** | [https://aistudio.google.com/apikey](https://aistudio.google.com/apikey)         |

### AI-Powered Features

- **Auto-Summarization** — When a document is uploaded, its text is extracted and sent to Gemini for a 2–3 sentence summary that is stored alongside the document.
- **Semantic Search** — Natural-language queries are compared against stored document summaries by the LLM, which returns the best-matching documents with a one-line explanation of relevance.

> **Without an API key**: The app runs normally, but AI summaries will show a placeholder message and search will return no results.

## Demo Login Credentials

Three pre-seeded accounts are available for testing the role hierarchy:

| Role             | Email               | Password  |
| ---------------- | ------------------- | --------- |
| **Member**       | employee@demo.com   | `demo123` |
| **Manager**      | manager@demo.com    | `demo123` |
| **Admin (CEO)**  | ceo@demo.com        | `demo123` |

## Known Limitations & Assumptions

- **SQLite** — Single-writer database; not suitable for high-concurrency production workloads. For production, consider migrating to PostgreSQL.
- **File Storage** — Documents are stored as BLOBs in SQLite. This works well for files under 10 MB but is not ideal for large-scale document management.
- **Render Free Tier** — Filesystem is ephemeral — the SQLite database and all data reset on each redeploy. The seed script ensures demo data is always available.
- **PDF Extraction** — Text extraction quality depends on PDF structure. Scanned/image-based PDFs may yield poor or no text, resulting in less useful AI summaries.
- **No Email Verification** — Signup does not require email confirmation.
- **No Password Reset** — There is no forgot-password or password-reset flow.
- **No Real-Time Updates** — The app uses traditional request/response — no WebSocket or live notifications.
- **AI Dependency** — Summarization and search features require a valid Google Gemini API key and network connectivity to Google's API.
- **Session Duration** — JWT tokens expire after 24 hours; users will need to log in again.

## Project Structure

```
collabhub/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app entry point
│   ├── config.py            # Environment configuration
│   ├── models.py            # SQLAlchemy database models
│   ├── auth.py              # Authentication & authorization
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── users.py         # Auth, user management, dashboard
│   │   ├── projects.py      # Project CRUD & member management
│   │   ├── documents.py     # Document upload, download, delete
│   │   └── ai.py            # AI summarization & search
│   ├── templates/           # Jinja2 HTML templates
│   │   ├── base.html
│   │   ├── login.html
│   │   ├── signup.html
│   │   ├── dashboard.html
│   │   ├── error.html
│   │   ├── search_results.html
│   │   ├── projects/
│   │   │   ├── list.html
│   │   │   ├── detail.html
│   │   │   └── form.html
│   │   ├── users/
│   │   │   └── list.html
│   │   └── audit/
│   │       └── log.html
│   └── static/
│       ├── css/
│       │   └── style.css
│       └── js/
│           └── main.js
├── seed.py                  # Database seeder with demo data
├── requirements.txt         # Pinned Python dependencies
├── .env.example             # Environment variable template
├── .gitignore
├── Procfile                 # Render deployment
└── README.md
```

<p align="center">
  Built with ❤️ using <a href="https://fastapi.tiangolo.com/">FastAPI</a> &amp; <a href="https://ai.google.dev/">Google Gemini</a>
</p>
