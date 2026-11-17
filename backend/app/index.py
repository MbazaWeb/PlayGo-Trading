"""Vercel entry point: PostgreSQL paper API and Deriv OAuth callback."""
from app.postgres_api import app
from app.deriv_oauth import router, page

from app.deriv_accounts import router as accounts_router
from app.deriv_demo_bot import router as demo_bot_router

app.include_router(router)
app.include_router(accounts_router)
app.include_router(demo_bot_router)


@app.get('/', include_in_schema=False)
def index():
    return page('PlayGo Trading API', '<p>The PostgreSQL paper API is running.</p><p><a href="/api/health">Health</a> / <a href="/api/ready">Database readiness</a> / <a href="/deriv/connect">Connect Deriv</a></p><small>Deriv bot execution is demo-account only. Real-account execution is disabled.</small>')
