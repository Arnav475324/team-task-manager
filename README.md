# TaskUS

A full-stack Flask web app for managing projects, tasks, and teams with role-based access control.

## Features
- User signup/login with Admin and Member roles
- Project creation and team assignment
- Task creation, assignment, and status tracking
- Dashboard with progress, overdue, and status summaries
- REST API endpoints for projects, tasks, and team membership

## Run locally
1. `python -m venv venv`
2. `venv\Scripts\activate`
3. `pip install -r requirements.txt`
4. `python app.py`
5. Open `http://127.0.0.1:5000`

## Deploy
1. Create a new project on Railway.
2. Connect your repository or upload the project files.
3. Set the environment variables:
   - `SECRET_KEY` — a secure random string
   - `DATABASE_URL` — optional if using a hosted database; defaults to SQLite locally
4. Railway will use `Procfile` to start the app: `web: python app.py`
5. Deploy and open the live URL.

### Notes
- The first registered user becomes `Admin`.
- If you want a production DB, set `DATABASE_URL` to your PostgreSQL or MySQL URI.
