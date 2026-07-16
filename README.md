<p align="center">
  <h1 align="center">CollabHub</h1>
  <p align="center">
    <strong>Enterprise Collaboration & Hierarchical Access Management Platform</strong>
  </p>
  <p align="center">
    <a href="https://collabhub-9cjl.onrender.com/"><strong>🚀 Live Deployment URL: https://collabhub-9cjl.onrender.com/</strong></a>
  </p>
  <p align="center">
    <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python"></a>
    <a href="https://fastapi.tiangolo.com/"><img src="https://img.shields.io/badge/FastAPI-0.115-009688?style=flat-square&logo=fastapi&logoColor=white" alt="FastAPI"></a>
    <a href="https://www.sqlite.org/"><img src="https://img.shields.io/badge/SQLite-Database-003B57?style=flat-square&logo=sqlite&logoColor=white" alt="SQLite"></a>
    <a href="https://ai.google.dev/"><img src="https://img.shields.io/badge/Gemini-3.5--flash-4285F4?style=flat-square&logo=google&logoColor=white" alt="Gemini"></a>
  </p>
</p>

---

CollabHub is a full-stack, multi-tenant enterprise collaboration platform. It offers hierarchical role-based access control, AI-powered document intelligence (cohesive project files summary, catch-up smart summary, semantic searches), real-time WebSockets messaging, and full audit logging. The entire system is built with FastAPI and server-rendered templates.

## Live Deployment

The application is deployed on Render and is accessible at:
👉 **[https://collabhub-9cjl.onrender.com/](https://collabhub-9cjl.onrender.com/)**

---

## Latest Features & Updates

### 1. Multi-Tenant Workspace Isolation
- **Organization Registration**: Public signup registers a new `Organization` (by entering an Organization Name) and automatically marks the registrant as the organization's CEO (Admin).
- **Data Isolation**: All projects, documents, logs, users, and conversations are strictly isolated by `organization_id` at the database and query boundary level. 
- **Dynamic Community Chats**: Each organization gets a dynamically initialized community chat room on setup, preventing cross-organization communication.

### 2. CEO Workspace Onboarding Setup
- **Onboarding Flow**: Newly registered CEOs are redirected to a dedicated Workspace Setup onboarding flow. 
- **Employee Provisioning**: CEOs can instantly add employees (managers, developers, members) to their organization, creating custom emails, roles, and temp passwords for them.
- **Persistent Access**: A permanent **Workspace Setup** link is added to the sidebar for CEO users to update the Gemini API Key or add more employees at any time.

### 3. Bring-Your-Own Gemini API Key (BYOK)
- All AI features (summarizing single documents, unified project file summaries, semantic search, and chat catch-up) run using the custom Google Gemini API Key configured by the organization's CEO during onboarding.

### 4. Real-Time Chat & WebSockets
- **DMs & Group Chats**: Users can start isolated direct messages or group chats with coworkers within the same organization.
- **WebSocket Broadcast**: Full WebSocket-backed real-time messaging with strict organization and membership verification during connection handshakes and message broadcasts.
- **Chat Catch-Up**: Summarizes recent chat logs into 3-4 key bullet points using the configured Gemini model (`gemini-3.5-flash`).

### 5. Indian Standard Time (IST) Clock
- All database timestamps are saved in UTC but formatted and rendered in **Indian Standard Time (IST, GMT+5:30)** using a centralized Jinja2 templates filter.

---

## Tech Stack

| Layer              | Technology                                                         |
| ------------------ | ------------------------------------------------------------------ |
| **Backend**        | Python 3.10+, FastAPI, Uvicorn, WebSockets                         |
| **Database**       | SQLite (single file, auto-created via SQLAlchemy ORM)               |
| **Frontend**       | Server-rendered HTML (Jinja2 templates), vanilla CSS, vanilla JavaScript |
| **Authentication** | JWT tokens in HttpOnly cookies, bcrypt password hashing            |
| **AI**             | Google Gemini (`gemini-3.5-flash`) via `google-genai` SDK          |
| **File Storage**   | SQLite BLOB (stored in-database)                                   |

---

## Setup Instructions

```bash
# 1. Clone the repository
git clone https://github.com/khost-07/Collabhub.git
cd Collabhub

# 2. Create and activate a virtual environment
python -m venv venv
venv\Scripts\activate     # Windows
source venv/bin/activate  # macOS/Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment variables
cp .env.example .env
# Edit .env and set your custom configurations (SECRET_KEY, DATABASE_URL)

# 5. Seed the database with demo organization data
python seed.py

# 6. Start the development server
uvicorn app.main:app --reload

# 7. Open your browser
# Visit http://localhost:8000
```

---

## Onboarding & Setup Instructions

1. **Sign Up**: Go to the `/signup` page. Enter your **Organization Name**, full name, email, and password.
2. **Setup Workspace**: Upon signup, you will be redirected to `/onboarding`.
3. **Configure API Key**: Input your **Google Gemini API Key** (retrieve one at [Google AI Studio](https://aistudio.google.com/apikey)).
4. **Provision Employees**: Fill in details under "Add Team Member" to register managers, senior developers, junior developers, and members with temporary passwords.
5. **Begin Collaborating**: Click **Finish Onboarding** to go to your dashboard, create projects, assign members, and upload documents!

---

## Demo Login Credentials

Demo credentials are seeded under the `"CollabHub Demo"` organization:

| Role             | Email               | Password  |
| ---------------- | ------------------- | --------- |
| **Admin (CEO)**  | ceo@demo.com        | `demo123` |
| **Manager**      | manager@demo.com    | `demo123` |
| **Senior Dev**   | srdev@demo.com      | `demo123` |
| **Junior Dev**   | jrdev@demo.com      | `demo123` |
| **Member**       | employee@demo.com   | `demo123` |
| **Guest**        | guest@demo.com      | `demo123` |

---

## Project Structure

```
collabhub/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI application entry point
│   ├── config.py            # Environment configuration
│   ├── models.py            # SQLAlchemy database models
│   ├── auth.py              # Authentication, authorization, audit logging
│   ├── common_templates.py  # Centralized Jinja2 templates config & IST filters
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── users.py         # Auth, onboarding, dashboard
│   │   ├── projects.py      # Project CRUD & member management
│   │   ├── documents.py     # Document upload, download, delete
│   │   ├── chat.py          # Real-time WebSocket conversations
│   │   └── ai.py            # AI summarization, search, chat catch-up
│   ├── templates/           # Jinja2 HTML templates
│   │   ├── base.html
│   │   ├── login.html
│   │   ├── signup.html
│   │   ├── dashboard.html
│   │   ├── error.html
│   │   ├── search_results.html
│   │   ├── chat.html
│   │   ├── onboarding.html
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
├── seed.py                  # Database seeder with demo organization data
├── requirements.txt         # Pinned Python dependencies
├── .env.example             # Environment variable template
├── .gitignore
├── Procfile                 # Render deployment script
└── README.md
```

<p align="center">
  Built with ❤️ using <a href="https://fastapi.tiangolo.com/">FastAPI</a> &amp; <a href="https://ai.google.dev/">Google Gemini</a>
</p>
