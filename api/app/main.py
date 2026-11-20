import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from . import auth
from .config import get_settings
from .db import create_schema, get_engine, session_factory
from . import proofs
from .routers import admin, approvals, assets, attachments, compliance, contracts_banking, documents, fleet, health, intake, inventory, io, photos, reports, requests, session, tasks, travel
from .workflow import run_escalations

log = logging.getLogger("executive_admin")


async def _escalation_loop(interval: int) -> None:
    while True:
        await asyncio.sleep(interval)
        try:
            async with session_factory()() as s:
                await run_escalations(s)
        except Exception:  # keep the loop alive; the next sweep retries
            log.exception("escalation sweep failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    task = None
    from .seed import seed, seed_production, seed_reference_data

    await create_schema()
    async with session_factory()() as s:
        if settings.is_dev:
            # Development convenience: the placeholder directory with "Sign in as".
            await seed(s)
        else:
            from .auth import bootstrap_admin

            if await seed_production(s):
                log.info("production starting data created")
            created = await bootstrap_admin(s)
            if created:
                log.warning("first Admin created for %s; they must change the password on first sign-in", created)
        await seed_reference_data(s)
        from .asset_ids import backfill_serials

        if n := await backfill_serials(s):
            log.info("gave %d existing assets an automatic serial number", n)
        from .routers.inventory import fold_stock_assets

        if n := await fold_stock_assets(s):
            log.info("folded %d asset records made by stock issues back into their stock lines", n)
        from .asset_ids import backfill_issue_refs

        if n := await backfill_issue_refs(s):
            log.info("grouped earlier issued assets into %d issuances", n)
    if settings.escalation_interval_s > 0:
        task = asyncio.create_task(_escalation_loop(settings.escalation_interval_s))
    yield
    if task:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
    await get_engine().dispose()


settings = get_settings()
app = FastAPI(
    title="Executive Admin API",
    version="1.1.1",
    lifespan=lifespan,
    # The interactive API docs are for development only.
    docs_url="/docs" if settings.is_dev else None,
    redoc_url=None,
    openapi_url="/openapi.json" if settings.is_dev else None,
)


@app.middleware("http")
async def same_origin_writes(request: Request, call_next):
    """Production: requests that change data must come from the app's own address (blocks cross-site forgery)."""
    if not settings.is_dev and request.method not in ("GET", "HEAD", "OPTIONS"):
        allowed = {o.rstrip("/") for o in ([settings.public_origin] if settings.public_origin else []) + list(settings.cors_origins)}
        origin = request.headers.get("origin")
        if origin is None:
            ref = request.headers.get("referer") or ""
            origin = "/".join(ref.split("/")[:3]) if ref else None
        if origin is None or origin.rstrip("/") not in allowed:
            return JSONResponse({"detail": {"message": "This request did not come from Executive Admin"}}, status_code=403)
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    return response
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth.router)
for r in (health, session, requests, attachments, approvals, tasks, admin, assets, inventory, fleet, compliance, travel, io, reports, documents, photos, intake, proofs):
    app.include_router(r.router)
app.include_router(contracts_banking.contracts)
app.include_router(contracts_banking.banking)
