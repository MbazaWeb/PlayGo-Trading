"""Vercel entry point: PostgreSQL paper API and Deriv OAuth callback."""
from app.postgres_api import app
from app.deriv_oauth import router, page

app.include_router(router)


@app.get('/', include_in_schema=False)
def index():
    return page('PlayGo Trading API', '<p>The PostgreSQL paper API is running.</p><p><a href="/api/health">Health</a> / <a href="/api/ready">Database readiness</a> / <a href="/deriv/connect">Connect Deriv</a></p><small>Paper only. Live execution is disabled.</small>')
