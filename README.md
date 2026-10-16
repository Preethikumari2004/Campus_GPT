# MCA CampusAI

A local campus portal for MCA students, faculty, and administrators. The frontend uses React and Vite; the backend uses FastAPI and PostgreSQL.

## Requirements

- Windows PowerShell
- Python 3.13 (or a compatible recent Python version)
- Node.js and npm
- PostgreSQL 18

## First-time setup

1. Start the PostgreSQL service.
2. From the project root, create the virtual environment and install backend packages:

    py -3.13 -m venv .venv
    & ".\.venv\Scripts\python.exe" -m pip install -r .\backend\requirements.txt

3. Copy .env.example to .env in the project root. Set the database URL, JWT secret, and admin API key. Keep the real .env private. If the database password contains @, encode it as %40 in the URL.
4. Install frontend packages once:

    cd .\frontend
    npm ci

## Run locally

Start PostgreSQL first. In VS Code, open two PowerShell terminals.

### Terminal 1: backend

    cd C:\path\to\MCA-campusAI\backend
    & "..\.venv\Scripts\python.exe" -m uvicorn main:app --reload --port 8001

Keep this terminal open. The API health check is http://127.0.0.1:8001/health; the interactive API page is http://127.0.0.1:8001/docs.

### Terminal 2: frontend

    cd C:\path\to\MCA-campusAI\frontend
    npm run dev

Open the Local address Vite prints, usually http://localhost:5173/. If 5173 is already in use, use the alternate Local address Vite prints.

To stop a server, focus its terminal and press Ctrl+C. If you will use the project again soon, PostgreSQL can remain running.

## Demo accounts

- Student: student_demo / student1234
- Faculty: faculty_demo / faculty1234
- Admin: admin_demo / admin1234

These are demo-only credentials. Change or remove them before any real deployment.

## CampusGPT behavior and current limits

- Uploaded documents are filtered by campus/course/user access before retrieval.
- Retrieval currently uses local keyword matching. The optional Groq chat API can phrase an answer when enabled, but if the key is missing, the API is disabled, or the provider is rate-limited, CampusGPT falls back to matching source sentences. This fallback is less conversational and may miss semantically related passages.
- Although embedding helper functions and a vector-index cache exist, they are not currently part of the active chat retrieval path. The GROQ_EMBEDDING_MODEL setting is therefore reserved and does not currently change search behavior.
- To avoid external AI requests, keep CAMPUSGPT_LOCAL_ONLY=true. To opt into Groq chat, provide GROQ_API_KEY and set CAMPUSGPT_LOCAL_ONLY=false; provider availability and limits apply.
- Treat answers as a guide and check official, current university notices for important decisions.

## Verify before a demo

From the project root, run the backend checks:

    .\.venv\Scripts\python.exe -m pytest -q

Build the frontend:

    cd .\frontend
    npm run build

## Common startup problems

- Connection refused on port 8001: the backend did not start. Read the first error in the backend terminal.
- Database connection error: check that PostgreSQL is Running and that .env has the correct database settings.
- Missing Python package: install from backend\requirements.txt using the project .venv Python.
- Frontend port in use: use the new Local address Vite prints, or stop the earlier Vite terminal with Ctrl+C.
- Native binding / application-control error from Vite: this may be a Windows device policy restriction; reinstalling packages may not resolve a policy block.

This project is a local demonstration MVP. It is not yet production-hardened; verify access control, demo credentials, document permissions, and current campus information before any real deployment.
