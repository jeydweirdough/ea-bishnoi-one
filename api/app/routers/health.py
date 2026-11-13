from fastapi import APIRouter
from sqlalchemy import text

from ..db import get_engine

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@router.get("/health/db")
async def health_db() -> dict:
    engine = get_engine()
    try:
        async with engine.connect() as conn:
            if engine.dialect.name == "sqlite":
                version = "SQLite " + (await conn.execute(text("select sqlite_version()"))).scalar_one()
            else:
                version = (await conn.execute(text("select version()"))).scalar_one().split(",")[0]
        return {"status": "ok", "dialect": engine.dialect.name, "server": version}
    except Exception as exc:  # surface the failure, not a stack trace
        return {"status": "error", "detail": type(exc).__name__}
