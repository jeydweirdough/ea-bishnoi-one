# Bishnoi One — Executive Admin

The corporate-services application for Bishnoi One (`EXECUTIVE-ADMIN.md`).

**Status: Phase 2 is complete.** Employee requests, approvals and administration, assets, equipment inventory, fleet, compliance, travel and immigration, contracts, banking and cards, import/export, official documents and reports all work against the database. See [`docs/PHASE-2-STATUS.md`](docs/PHASE-2-STATUS.md) for what works, how it was verified, and the known gaps.

```
web/   Next.js 16 (App Router, TypeScript, Tailwind v4), installable PWA
api/   FastAPI + SQLAlchemy (async). Neon/Postgres via DATABASE_URL; SQLite file in local development
docs/  Phase status and decisions
```

## Run it locally

Start both parts. The web app forwards `/api/*` to the API, so the browser only ever talks to one origin.

```bash
# 1. API (port 8000)
cd api
python -m venv .venv
.venv/Scripts/activate            # Windows; use source .venv/bin/activate elsewhere
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

In development the API creates its tables and seeds a placeholder directory (companies, departments, people, the two approval templates and SLA defaults) into `api/executive_admin.db` on first start. To start fresh, stop the API and delete that file and `api/uploads/`.

```bash
# 2. Web (port 3000)
cd web
npm install
npm run dev                       # http://localhost:3000
# production / PWA check:  npm run build && npm start
```

If the API is not on `http://127.0.0.1:8000`, set `API_URL` for the web app.

### Signing in (development)

Open the app and pick a person from the development directory. You can switch at any time from the avatar menu. Useful people to try:

| Person | What they show |
|---|---|
| Carlo Diaz (Employee) | Raise concerns, request supplies, track and confirm |
| Dana Cruz (Sales Head, approver) | First approval stage for Sales requests; Approval Inbox |
| Jasmine, Mira, Malhou | Later stages of the staff-concern chain |
| Chief Operating Officer, Naresh | Later stages of the item-request chain |
| Alex Reyes (Admin) | Operations overview, queues, assignment, workflows, SLA, audit, grants |
| Bea Santos (Assistant) | Sees only work assigned to her; tasks |
| Gio Lim / Hana Uy (2MG) | Second company, for isolation checks |

The browser sends only the employee number (`ea_user` cookie). The API reads the role, approval grant, delegations and company access from the database. In production, sign-in comes from One Admin, and outside `ENV=development` the API refuses every request until that integration exists.

### Neon / Postgres

Copy `api/.env.example` to `api/.env` and set `DATABASE_URL` to the Neon connection string. `sslmode=require` is converted for asyncpg automatically. Before the first production deployment, add Alembic migrations (see the status doc).

## Tests

```bash
cd api && pytest                  # 102 API tests (incl. sign-in, the request link, proof of receipt, issuing several items as one, automatic serials, document reading, added people and item photos): requests, approvals, SLA, tasks, audit, assets, inventory, fleet, compliance, travel, contracts, banking, import/export, documents, reports
cd web && npx eslint src && npm run build
```

## Where things live

| What | File |
|---|---|
| Navigation, codes, Coming Soon content | `web/src/lib/nav.ts` |
| Which modules are live | `web/src/lib/modules.ts` |
| API client, types, formatting | `web/src/lib/api.ts` |
| Request form, list, detail, approval route | `web/src/components/requests/` |
| Employee pages | `web/src/components/self/self-pages.tsx` |
| Inbox, queues, overview, tasks, admin screens | `web/src/components/ops/` |
| Assets (registry, assignment, transfers, repairs, receiving, issuance form) | `web/src/components/assets/` |
| Fleet (vehicles, renewals, services, cards, RFID, Finance hand-offs) | `web/src/components/fleet/` |
| Compliance (registrations, BOC, renewal calendar, documents) | `web/src/components/compliance/` |
| Travel (flights, hotels, requirements, passports & visas) | `web/src/components/travel/` |
| Equipment Inventory (stock, requests to fill, counts, movements) | `web/src/components/inventory/` |
| Contracts (leases, staff houses, renewals, rent, lessors) | `web/src/components/contracts/` |
| Banking & Cards (cards, applications, documentation, Finance) | `web/src/components/banking/` |
| Import wizard and export dialog | `web/src/components/io/data-tools.tsx` |
| Documents panel and register | `web/src/components/documents/` |
| Reports hub (catalogue, viewer, period documents, import history) | `web/src/components/reports/` |
| Schema-driven record dialogs | `web/src/components/ui/record-form.tsx` |
| Shared controls, status badges, dialogs, toasts | `web/src/components/ui/` |
| Route redirects (navigation only) | `web/src/lib/access.ts`, `web/src/proxy.ts` |
| Data model | `api/app/models.py`, `api/app/models_ops.py`, `api/app/models_ops2.py`, `api/app/models_ops3.py` |
| Import/export field registry | `api/app/datasets.py` |
| PDF document engine | `api/app/pdf.py` |
| Lifecycle, approval routing, escalation | `api/app/workflow.py` |
| Identity and permission checks | `api/app/security.py` |
| Endpoints | `api/app/routers/` |
| Seed directory | `api/app/seed.py` |

## Design

Monochrome Product world, Poppins (SIL OFL) via `next/font/google`. See `DESIGN.md`: one neutral scale, an accent kept for "you are here" and live states, one red used only for overdue, rejected and destructive actions, and an icon for every module.

## Production

Docker Compose stack (web, api, Postgres) for Coolify on bishnoi-one-server at https://ea.bishnoi.ai: see [docs/DEPLOY.md](docs/DEPLOY.md) and [.env.production.example](.env.production.example).

Run the API tests against Postgres: `TEST_DATABASE_URL=postgresql://user@host:port/empty_db pytest`.
