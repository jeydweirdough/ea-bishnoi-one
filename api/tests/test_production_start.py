"""A production start on an empty database: starting data and the first Admin, no placeholder people."""

import asyncio

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import get_settings
from app.db import Base


def test_empty_database_gets_starting_data_and_first_admin(tmp_path, monkeypatch):
    from app import models, models_ops, models_ops2, models_ops3  # noqa: F401  (register tables)
    from app.auth import bootstrap_admin, verify_password
    from app.models import Company, Employee, WorkflowStage
    from app.seed import seed_production

    s = get_settings()
    monkeypatch.setattr(s, "bootstrap_admin_email", "Admin@Bishnoi.ai")
    monkeypatch.setattr(s, "bootstrap_admin_password", "First-Admin-Pass-1")
    monkeypatch.setattr(s, "bootstrap_admin_name", "Ea Admin")

    async def run():
        engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'prod.db').as_posix()}")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as db:
            assert await seed_production(db) is True
            assert await seed_production(db) is False  # idempotent
            assert await bootstrap_admin(db) == "admin@bishnoi.ai"
            assert await bootstrap_admin(db) is None  # an Admin can already sign in
            people = (await db.execute(select(Employee))).scalars().all()
            companies = (await db.execute(select(func.count()).select_from(Company))).scalar_one()
            unassigned = (await db.execute(select(func.count()).where(WorkflowStage.approver_type == "employee", WorkflowStage.approver_id.is_(None)))).scalar_one()
        await engine.dispose()
        return people, companies, unassigned

    people, companies, unassigned = asyncio.run(run())
    assert len(people) == 1  # only the first Admin: no placeholder directory in production
    admin = people[0]
    assert admin.role == "admin" and admin.email == "admin@bishnoi.ai" and admin.must_change_password
    assert verify_password("First-Admin-Pass-1", admin.password_hash)
    assert sorted(admin.company_access) == ["2MG", "GPI"]
    assert companies == 2 and unassigned == 5  # named approver stages wait for Admin to assign them
