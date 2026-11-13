"""
Email + password sign-in for production, until One Admin single sign-on is connected.

- Passwords are hashed with scrypt (Python standard library); the password itself is never stored or logged.
- A successful sign-in creates a server-side session. The browser gets a random token in an
  HttpOnly, Secure, SameSite=Lax cookie; only the token's SHA-256 is stored, so a database leak
  cannot be replayed as a cookie.
- Sessions end after `session_idle_hours` without activity, or `session_max_days` in any case.
- An account locks for `login_lock_minutes` after `login_max_failures` wrong passwords; one address
  is also slowed down after many failures across accounts. Error messages never reveal whether an
  email exists.
- Admin creates accounts and hands out a one-time temporary password; the user must change it on
  first sign-in. Changing or resetting a password signs out every other session.

In development the API keeps the "Sign in as" directory instead (see security.py).
"""

import base64
import hashlib
import hmac
import secrets
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select

from .config import get_settings
from .core import audit, bad_request
from .models import AuthSession, Company, Employee, Role
from .security import CurrentPrincipal, Session

router = APIRouter(prefix="/api/v1/auth", tags=["sign-in"])

COOKIE = "ea_session"
MIN_LENGTH = 10
_N, _R, _P = 2**14, 8, 1


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def aware(dt: datetime | None) -> datetime | None:
    """SQLite returns naive datetimes; treat stored values as UTC."""
    return dt.replace(tzinfo=timezone.utc) if dt and dt.tzinfo is None else dt


# ------------------------------------------------------------------ passwords


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${_N}${_R}${_P}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        # Same work as a real check, so response time does not reveal unknown emails.
        hashlib.scrypt(password.encode(), salt=b"0" * 16, n=_N, r=_R, p=_P, dklen=32)
        return False
    try:
        _, n, r, p, salt, dk = stored.split("$")
        got = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p), dklen=32)
        return hmac.compare_digest(got, base64.b64decode(dk))
    except (ValueError, TypeError):
        return False


def password_problem(password: str, email: str | None = None) -> str | None:
    if len(password) < MIN_LENGTH:
        return f"Use at least {MIN_LENGTH} characters"
    if len(password) > 200:
        return "Use at most 200 characters"
    if email and password.lower() == email.lower():
        return "Don't use your email address as the password"
    if len(set(password)) < 4:
        return "Use a less predictable password"
    return None


def temporary_password() -> str:
    """12 characters, no look-alikes (0/O, 1/l/I), easy to read out or type from a phone."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789"
    return "".join(secrets.choice(alphabet) for _ in range(12))


# ------------------------------------------------------------------ sessions


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def principal_from_cookie(session, token: str | None) -> Employee | None:
    """The signed-in employee for a session cookie, refreshing its last activity; None when invalid."""
    if not token:
        return None
    s = get_settings()
    row = (await session.execute(select(AuthSession).where(AuthSession.token_hash == token_hash(token)))).scalar_one_or_none()
    if row is None:
        return None
    now = utcnow()
    if aware(row.expires_at) <= now or aware(row.last_seen_at) + timedelta(hours=s.session_idle_hours) <= now:
        await session.delete(row)
        await session.commit()
        return None
    emp = await session.get(Employee, row.employee_id)
    if emp is None or not emp.active or emp.source == "added":
        return None
    if now - aware(row.last_seen_at) > timedelta(minutes=5):  # avoid a write on every request
        row.last_seen_at = now
        await session.commit()
    return emp


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    return (fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "unknown"))[:64]


def set_cookie(response: Response, token: str, max_age: int) -> None:
    response.set_cookie(COOKIE, token, max_age=max_age, httponly=True, secure=get_settings().cookie_secure, samesite="lax", path="/")


# Failures per client address in the last 15 minutes (in-process; the API runs one worker).
_ip_failures: dict[str, deque] = defaultdict(deque)
IP_WINDOW_S, IP_MAX = 15 * 60, 30


def _ip_blocked(ip: str) -> bool:
    q = _ip_failures[ip]
    cutoff = time.monotonic() - IP_WINDOW_S
    while q and q[0] < cutoff:
        q.popleft()
    return len(q) >= IP_MAX


# ------------------------------------------------------------------ endpoints


@router.get("/mode")
async def mode() -> dict:
    """Which sign-in the web app should show."""
    return {"mode": "dev" if get_settings().is_dev else "password"}


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=1, max_length=200)


def signed_in_out(e: Employee) -> dict:
    return {"employee_no": e.employee_no, "name": e.name, "role": e.role, "approver": bool(e.can_approve), "must_change_password": bool(e.must_change_password)}


@router.post("/login")
async def login(body: LoginIn, request: Request, response: Response, session: Session) -> dict:
    s = get_settings()
    ip = client_ip(request)
    wrong = HTTPException(status.HTTP_401_UNAUTHORIZED, {"message": "Email or password is incorrect"})
    if _ip_blocked(ip):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, {"message": "Too many attempts from this device. Try again in 15 minutes."})
    email = body.email.strip().lower()
    emp = (
        await session.execute(
            select(Employee).where(func.lower(Employee.email) == email, Employee.active.is_(True), Employee.source != "added")
        )
    ).scalars().first()
    now = utcnow()
    if emp is not None and aware(emp.locked_until) and aware(emp.locked_until) > now:
        verify_password(body.password, None)
        mins = max(1, int((aware(emp.locked_until) - now).total_seconds() // 60) + 1)
        raise HTTPException(status.HTTP_423_LOCKED, {"message": f"Too many wrong passwords. This account is locked for {mins} more minute{'s' if mins != 1 else ''}, or ask Admin to reset it."})
    if emp is None or not verify_password(body.password, emp.password_hash):
        _ip_failures[ip].append(time.monotonic())
        if emp is not None:
            emp.failed_logins = (emp.failed_logins or 0) + 1
            locked = emp.failed_logins >= s.login_max_failures
            if locked:
                emp.locked_until = now + timedelta(minutes=s.login_lock_minutes)
                emp.failed_logins = 0
            await audit(session, actor_id=emp.id, action="auth.login_failed", entity_type="employee", entity_id=emp.id, entity_ref=emp.employee_no, data={"ip": ip, "locked": locked})
            await session.commit()
        raise wrong
    emp.failed_logins = 0
    emp.locked_until = None
    emp.last_login_at = now
    token = secrets.token_urlsafe(32)
    max_age = s.session_max_days * 86400
    session.add(
        AuthSession(
            token_hash=token_hash(token), employee_id=emp.id, created_at=now, last_seen_at=now,
            expires_at=now + timedelta(seconds=max_age), ip=ip, user_agent=(request.headers.get("user-agent") or "")[:200],
        )
    )
    await audit(session, actor_id=emp.id, action="auth.login", entity_type="employee", entity_id=emp.id, entity_ref=emp.employee_no, data={"ip": ip})
    await session.commit()
    set_cookie(response, token, max_age)
    return signed_in_out(emp)


@router.post("/logout", status_code=204)
async def logout(request: Request, response: Response, session: Session) -> None:
    token = request.cookies.get(COOKIE)
    if token:
        await session.execute(delete(AuthSession).where(AuthSession.token_hash == token_hash(token)))
        await session.commit()
    response.delete_cookie(COOKIE, path="/", secure=get_settings().cookie_secure, httponly=True, samesite="lax")


class PasswordIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=1, max_length=200)


@router.post("/password")
async def change_password(body: PasswordIn, principal: CurrentPrincipal, request: Request, session: Session) -> dict:
    emp = principal.employee
    if not verify_password(body.current_password, emp.password_hash):
        raise bad_request({"message": "The current password is incorrect", "fields": {"current_password": "Incorrect"}})
    problem = password_problem(body.new_password, emp.email)
    if problem:
        raise bad_request({"message": problem, "fields": {"new_password": problem}})
    if body.new_password == body.current_password:
        raise bad_request({"message": "Choose a new password", "fields": {"new_password": "Same as the current password"}})
    emp.password_hash = hash_password(body.new_password)
    emp.password_changed_at = utcnow()
    emp.must_change_password = False
    # Sign out every other browser.
    keep = token_hash(request.cookies.get(COOKIE) or "")
    await session.execute(delete(AuthSession).where(AuthSession.employee_id == emp.id, AuthSession.token_hash != keep))
    await audit(session, actor_id=emp.id, action="auth.password_changed", entity_type="employee", entity_id=emp.id, entity_ref=emp.employee_no)
    await session.commit()
    return signed_in_out(emp)


# ------------------------------------------------------------------ admin helpers (used by routers/admin.py)


async def end_sessions(session, employee_id: int) -> None:
    await session.execute(delete(AuthSession).where(AuthSession.employee_id == employee_id))


async def bootstrap_admin(session) -> str | None:
    """Create the first Admin from settings when no Admin can sign in yet. Returns what happened."""
    s = get_settings()
    if not (s.bootstrap_admin_email and s.bootstrap_admin_password):
        return None
    can_sign_in = (
        await session.execute(select(Employee.id).where(Employee.role == Role.admin, Employee.active.is_(True), Employee.password_hash.is_not(None)))
    ).first()
    if can_sign_in:
        return None
    problem = password_problem(s.bootstrap_admin_password, s.bootstrap_admin_email)
    if problem:
        raise RuntimeError(f"BOOTSTRAP_ADMIN_PASSWORD: {problem}")
    company = (await session.execute(select(Company).where(Company.code == s.bootstrap_company_code))).scalar_one_or_none()
    if company is None:
        company = (await session.execute(select(Company).order_by(Company.id))).scalars().first()
    if company is None:
        raise RuntimeError("No company exists for the first Admin")
    email = s.bootstrap_admin_email.strip().lower()
    emp = (await session.execute(select(Employee).where(func.lower(Employee.email) == email))).scalars().first()
    if emp is None:
        n = (await session.execute(select(func.count()).select_from(Employee))).scalar_one()
        emp = Employee(employee_no=f"EA-{n + 1:04d}", name=s.bootstrap_admin_name, email=email, company_id=company.id, designation="Executive Admin")
        session.add(emp)
    emp.role = Role.admin
    emp.active = True
    emp.company_access = sorted({c for (c,) in (await session.execute(select(Company.code))).all()})
    emp.password_hash = hash_password(s.bootstrap_admin_password)
    emp.must_change_password = True
    await session.flush()
    await audit(session, actor_id=None, action="auth.bootstrap_admin", entity_type="employee", entity_id=emp.id, entity_ref=emp.employee_no, data={"email": email})
    await session.commit()
    return email
