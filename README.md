# PlayGo Trading

## Project layout

- `frontend/` - Next.js, React, TypeScript, Tailwind CSS, public assets, frontend tests, and scripts.
- `backend/` - FastAPI, Python trading modules, workers, SQL, backend tests, scripts, and Docker configuration.
- `supabase/` - Supabase configuration and migrations.
- `docs/` - Architecture and operations documentation.
- `.env` - Shared local environment configuration. Never commit credentials.

## Run the frontend

```powershell
cd frontend
npm run dev
```

## Run the backend

```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.index:app --host 127.0.0.1 --port 8001
```

The Deriv workspace requires the `app.index:app` entry point; `app.postgres_api:app` does not register Deriv OAuth or account routes. Set `CORS_ORIGINS` in the repository-root `.env` to include `http://localhost:3000,http://127.0.0.1:3000` when using the Next.js frontend.
