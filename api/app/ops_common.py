"""Helpers shared by the asset and fleet routers."""

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select

from .core import bad_request, conflict, forbidden, not_found
from .models import Company, Department, Employee
from .security import Principal


def money(v: Decimal | None) -> str | None:
    return None if v is None else f"{Decimal(v):.2f}"


def day(v: date | None) -> str | None:
    return v.isoformat() if v else None


def days_until(v: date | None) -> int | None:
    return None if v is None else (v - date.today()).days


async def company_for(session, principal: Principal, company_id: int | None) -> int:
    cid = company_id or principal.employee.company_id
    if cid not in principal.company_ids:
        raise forbidden("You have no access to that company")
    if await session.get(Company, cid) is None:
        raise bad_request({"message": "Unknown company", "fields": {"company_id": "Not found"}})
    return cid


async def scoped(session, model, record_id: int, principal: Principal, *, lock: bool = False):
    """Load a company-owned record the staff principal may see, or 404. `lock` row-locks it for a read-modify-write."""
    stmt = select(model).where(model.id == record_id).execution_options(populate_existing=True)
    if lock:
        stmt = stmt.with_for_update(of=model)  # lock this row only (Postgres refuses to lock outer-joined relations)
    rec = (await session.execute(stmt)).scalar_one_or_none()
    if rec is None or rec.company_id not in principal.company_ids:
        raise not_found()
    return rec


async def employee_in(session, employee_id: int | None, company_id: int, field: str) -> Employee | None:
    if employee_id is None:
        return None
    emp = await session.get(Employee, employee_id)
    if emp is None or not emp.active:
        raise bad_request({"message": "Unknown employee", "fields": {field: "Not found"}})
    company = await session.get(Company, company_id)
    if emp.company_id != company_id and company.code not in (emp.company_access or []):
        raise bad_request({"message": f"{emp.name} is not in this company", "fields": {field: "Wrong company"}})
    return emp


async def department_in(session, department_id: int | None, company_id: int) -> Department | None:
    if department_id is None:
        return None
    d = await session.get(Department, department_id)
    if d is None or d.company_id != company_id:
        raise bad_request({"message": "That department belongs to another company", "fields": {"department_id": "Wrong company"}})
    return d


def check_version(record, version: int | None):
    if version is not None and version != record.version:
        raise conflict("This record changed since you opened it. Reload to see the latest version.")


async def count(session, stmt) -> int:
    return (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
