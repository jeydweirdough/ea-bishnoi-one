"""
Development directory and starting configuration.

Companies, departments and people here stand in for One Admin / People until
that integration lands; every name is a placeholder to be replaced. Workflow
templates mirror EXECUTIVE-ADMIN.md §6. SLA hours are configurable starting
values (Administration › Priorities & SLA), not policy. No requests, tasks or
other business records are seeded: dashboards only count what users create.

Run: python -m app.seed
"""

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db import create_schema, session_factory
from .models import Company, Department, Employee, Role, SlaPolicy, WorkflowStage, WorkflowTemplate

COMPANIES = [("GPI", "Getmeds Philippines Inc."), ("2MG", "2MG")]
DEPARTMENTS = [
    ("GPI", "ADM", "Executive Admin"),
    ("GPI", "OPS", "Operations"),
    ("GPI", "SAL", "Sales"),
    ("GPI", "IT", "IT"),
    ("GPI", "FIN", "Finance"),
    ("2MG", "OPS", "Operations"),
]
# employee_no, name, designation, company, dept, role, can_approve, company_access, delegations
PEOPLE = [
    ("EA-0001", "Alex Reyes", "Executive Admin Manager", "GPI", "ADM", Role.admin, False, ["GPI", "2MG"], {}),
    ("EA-0002", "Bea Santos", "Admin Assistant", "GPI", "ADM", Role.assistant, False, ["GPI"], {"assign": False, "set_priority": False}),
    ("EA-0101", "Carlo Diaz", "Sales Associate", "GPI", "SAL", Role.employee, False, [], {}),
    ("EA-0102", "Dana Cruz", "Sales Head", "GPI", "SAL", Role.employee, True, [], {}),
    ("EA-0103", "Eli Navarro", "IT Specialist", "GPI", "IT", Role.employee, False, [], {}),
    ("EA-0104", "Fe Ramos", "IT Head", "GPI", "IT", Role.employee, True, [], {}),
    ("EA-0105", "Ivy Tan", "Operations Head", "GPI", "OPS", Role.employee, True, [], {}),
    ("EA-0201", "Naresh", "Executive approver", "GPI", None, Role.employee, True, [], {}),
    ("EA-0202", "Chief Operating Officer", "COO", "GPI", None, Role.employee, True, [], {}),
    ("EA-0203", "Jasmine", "Staff concerns approver", "GPI", None, Role.employee, True, [], {}),
    ("EA-0204", "Mira", "Staff concerns approver", "GPI", None, Role.employee, True, [], {}),
    ("EA-0205", "Malhou", "Staff concerns approver", "GPI", None, Role.employee, True, [], {}),
    ("EA-0301", "Gio Lim", "Operations Staff", "2MG", "OPS", Role.employee, False, [], {}),
    ("EA-0302", "Hana Uy", "Operations Head", "2MG", "OPS", Role.employee, True, [], {}),
]
HEADS = {("GPI", "SAL"): "EA-0102", ("GPI", "IT"): "EA-0104", ("GPI", "OPS"): "EA-0105", ("2MG", "OPS"): "EA-0302"}
SLA = [("low", 48, 240, 48), ("normal", 24, 120, 24), ("high", 8, 48, 12), ("critical", 2, 24, 4)]


async def seed(session: AsyncSession) -> bool:
    if (await session.execute(select(Company.id))).first():
        return False
    companies = {code: Company(code=code, name=name) for code, name in COMPANIES}
    session.add_all(companies.values())
    await session.flush()
    depts = {}
    for c, code, name in DEPARTMENTS:
        d = Department(company_id=companies[c].id, code=code, name=name)
        session.add(d)
        depts[(c, code)] = d
    await session.flush()
    people = {}
    for no, name, desig, c, dept, role, approve, access, deleg in PEOPLE:
        e = Employee(
            employee_no=no,
            name=name,
            designation=desig,
            company_id=companies[c].id,
            department_id=depts[(c, dept)].id if dept else None,
            role=role,
            can_approve=approve,
            company_access=access,
            delegations=deleg,
        )
        session.add(e)
        people[no] = e
    await session.flush()
    for key, no in HEADS.items():
        depts[key].head_id = people[no].id

    items = WorkflowTemplate(
        key="items",
        name="Item Request Approval",
        description="Supplies, assets and purchases (EXECUTIVE-ADMIN.md §6.1).",
        kinds=["supplies", "asset", "local_purchase"],
        processing=["Executive Admin Processing", "Purchase / Fulfillment", "Receiving", "Issuance", "Completed"],
    )
    items.stages = [
        WorkflowStage(position=0, name="Approval Head", approver_type="department_head"),
        WorkflowStage(position=1, name="COO", approver_type="employee", approver_id=people["EA-0202"].id),
        WorkflowStage(position=2, name="Sir Naresh", approver_type="employee", approver_id=people["EA-0201"].id),
    ]
    concerns = WorkflowTemplate(
        key="concerns",
        name="Staff Concern Approval",
        description="Concerns, repairs and other requests (EXECUTIVE-ADMIN.md §6.2).",
        kinds=["concern", "repair", "other"],
        processing=["Executive Admin Processing", "Resolution", "Completed"],
    )
    concerns.stages = [
        WorkflowStage(position=0, name="Department Head", approver_type="department_head"),
        WorkflowStage(position=1, name="Jasmine", approver_type="employee", approver_id=people["EA-0203"].id),
        WorkflowStage(position=2, name="Ma'am Mira", approver_type="employee", approver_id=people["EA-0204"].id),
        WorkflowStage(position=3, name="Ma'am Malhou", approver_type="employee", approver_id=people["EA-0205"].id),
    ]
    session.add_all([items, concerns])
    for p, resp, res, every in SLA:
        session.add(SlaPolicy(priority=p, response_hours=resp, resolution_hours=res, escalate_every_hours=every))
    await session.commit()
    return True


TRAVEL_REQUIREMENTS = [
    # EXECUTIVE-ADMIN.md §11: starting checklist, configurable in Travel › Travel Requirements.
    ("domestic", None, "Valid government ID with date of birth", "Accepted by the airline for domestic check-in."),
    ("international", None, "Passport valid 6+ months after return", None),
    ("international", None, "Visa or entry permit, if the destination requires one", "Check the destination's current rules before ticketing."),
    ("international", None, "Return or onward ticket", None),
    ("international", None, "Travel authorization approved", None),
]


async def seed_production(session: AsyncSession) -> bool:
    """Production starting point: companies, departments, approval routes, SLA and travel lists.

    No people: the first Admin comes from BOOTSTRAP_ADMIN_* and adds everyone else. Named approval
    stages start unassigned; Admin assigns them in Settings › Approval routes (requests reaching an
    unassigned stage alert Admin instead of stalling silently). Idempotent: does nothing once a
    company exists.
    """
    if (await session.execute(select(Company.id))).first():
        return False
    companies = {code: Company(code=code, name=name) for code, name in COMPANIES}
    session.add_all(companies.values())
    await session.flush()
    for c, code, name in DEPARTMENTS:
        session.add(Department(company_id=companies[c].id, code=code, name=name))
    items = WorkflowTemplate(
        key="items",
        name="Item Request Approval",
        description="Supplies, assets and purchases (EXECUTIVE-ADMIN.md §6.1).",
        kinds=["supplies", "asset", "local_purchase"],
        processing=["Executive Admin Processing", "Purchase / Fulfillment", "Receiving", "Issuance", "Completed"],
    )
    items.stages = [
        WorkflowStage(position=0, name="Approval Head", approver_type="department_head"),
        WorkflowStage(position=1, name="COO", approver_type="employee"),
        WorkflowStage(position=2, name="Sir Naresh", approver_type="employee"),
    ]
    concerns = WorkflowTemplate(
        key="concerns",
        name="Staff Concern Approval",
        description="Concerns, repairs and other requests (EXECUTIVE-ADMIN.md §6.2).",
        kinds=["concern", "repair", "other"],
        processing=["Executive Admin Processing", "Resolution", "Completed"],
    )
    concerns.stages = [
        WorkflowStage(position=0, name="Department Head", approver_type="department_head"),
        WorkflowStage(position=1, name="Jasmine", approver_type="employee"),
        WorkflowStage(position=2, name="Ma'am Mira", approver_type="employee"),
        WorkflowStage(position=3, name="Ma'am Malhou", approver_type="employee"),
    ]
    session.add_all([items, concerns])
    for p, resp, res, every in SLA:
        session.add(SlaPolicy(priority=p, response_hours=resp, resolution_hours=res, escalate_every_hours=every))
    await session.commit()
    return True


async def seed_reference_data(session: AsyncSession) -> None:
    """Idempotent starting lists that later releases may add to."""
    from .models_ops2 import TravelRequirement

    if not (await session.execute(select(TravelRequirement.id))).first():
        for i, (tt, country, name, desc) in enumerate(TRAVEL_REQUIREMENTS):
            session.add(TravelRequirement(travel_type=tt, country=country, name=name, description=desc, position=i))
        await session.commit()


async def main() -> None:
    await create_schema()
    async with session_factory()() as s:
        print("seeded" if await seed(s) else "already seeded")
        await seed_reference_data(s)


if __name__ == "__main__":
    asyncio.run(main())
