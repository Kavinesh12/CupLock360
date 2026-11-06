from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.core.config import get_settings
from app.core.db import engine
from app.modules.audit.router import router as audit_router
from app.modules.auth.router import router as auth_router
from app.modules.crm.router import router as crm_router
from app.modules.items.router import router as items_router
from app.modules.masters.router import router as masters_router
from app.modules.org.router import router as org_router
from app.modules.users.router import router as users_router

settings = get_settings()

app = FastAPI(
    title="CUPLOCK 360° API",
    version="0.1.0",
    description="Scaffolding rental, inventory and financial control platform",
    docs_url=None if settings.is_prod else "/docs",
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["Authorization", "Content-Type"],
)

API = "/api/v1"
app.include_router(auth_router, prefix=API)
app.include_router(users_router, prefix=API)
app.include_router(org_router, prefix=API)
app.include_router(audit_router, prefix=API)
app.include_router(masters_router, prefix=API)
app.include_router(items_router, prefix=API)
app.include_router(crm_router, prefix=API)


if settings.env == "dev":
    # Dev-only: lets you read console-delivered OTPs until SMS/email is configured. Never mounted in prod/test.
    from app.services.notify import DEV_OUTBOX

    @app.get(f"{API}/dev/otp-outbox", tags=["dev"])
    def dev_otp_outbox():
        return list(reversed(DEV_OUTBOX[-10:]))


@app.get("/health", tags=["system"])
def health():
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok"}
