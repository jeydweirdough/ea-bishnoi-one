"""
Server-side identity and permission checks.

Development: the signed-in user comes from the `ea_user` cookie (set by the web
app's development sign-in menu) or the `X-EA-User` header, both holding an
employee number.

Production: identity comes only from the `ea_session` cookie created by email +
password sign-in (app/auth.py); the development cookie and header are ignored.
One Admin single sign-on will replace the password step later.

Either way, role, approval grant, delegations and company access are read from
the database, never from the client.
"""

from dataclasses import dataclass, field
from typing import Annotated

from fastapi import Cookie, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import get_settings
from .db import get_session
from .models import Employee, Role

Session = Annotated[AsyncSession, Depends(get_session)]


@dataclass
class Principal:
    employee: Employee
    company_ids: set[int] = field(default_factory=set)

    @property
    def id(self) -> int:
        return self.employee.id

    @property
    def role(self) -> Role:
        return Role(self.employee.role)

    @property
    def is_admin(self) -> bool:
        return self.role is Role.admin

    @property
    def is_staff(self) -> bool:
        return self.role in (Role.admin, Role.assistant)

    @property
    def approver(self) -> bool:
        return bool(self.employee.can_approve)

    def delegated(self, capability: str) -> bool:
        return bool((self.employee.delegations or {}).get(capability))

    def can(self, capability: str) -> bool:
        """Admin holds operational capabilities; Assistants only when delegated."""
        return self.is_admin or (self.role is Role.assistant and self.delegated(capability))


# While a temporary password is unchanged, only these paths work (the web app shows "Choose a new password").
PASSWORD_CHANGE_PATHS = ("/api/v1/auth/", "/api/v1/me")


async def get_principal(
    request: Request,
    session: Session,
    ea_user: Annotated[str | None, Cookie()] = None,
    x_ea_user: Annotated[str | None, Header()] = None,
    ea_session: Annotated[str | None, Cookie()] = None,
) -> Principal:
    if get_settings().is_dev:
        employee_no = x_ea_user or ea_user
        if not employee_no:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in to continue")
        employee = (
            await session.execute(select(Employee).where(Employee.employee_no == employee_no, Employee.active.is_(True), Employee.source != "added"))  # added people never sign in
        ).scalar_one_or_none()
        if employee is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unknown or inactive user")
    else:
        from .auth import principal_from_cookie

        employee = await principal_from_cookie(session, ea_session)
        if employee is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in to continue")
        if employee.must_change_password and not request.url.path.startswith(PASSWORD_CHANGE_PATHS):
            raise HTTPException(status.HTTP_403_FORBIDDEN, {"message": "Choose a new password to continue", "code": "password_change_required"})
    company_ids = {employee.company_id}
    if employee.role in (Role.admin, Role.assistant) and employee.company_access:
        from .models import Company

        rows = await session.execute(select(Company.id).where(Company.code.in_(employee.company_access)))
        company_ids |= {r for (r,) in rows}
    return Principal(employee=employee, company_ids=company_ids)


CurrentPrincipal = Annotated[Principal, Depends(get_principal)]


def require_roles(*roles: Role):
    def check(principal: CurrentPrincipal) -> Principal:
        if principal.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Not permitted for this user type")
        return principal

    return check


def require_approver(principal: CurrentPrincipal) -> Principal:
    if not principal.approver:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Approval duties have not been granted")
    return principal


Staff = Annotated[Principal, Depends(require_roles(Role.admin, Role.assistant))]
AdminOnly = Annotated[Principal, Depends(require_roles(Role.admin))]
Approver = Annotated[Principal, Depends(require_approver)]
