# Deploying Executive Admin to https://ea.bishnoi.ai

Target: **Coolify on bishnoi-one-server**, behind the existing Cloudflare Tunnel.

The tunnel already sends `*.bishnoi.ai` to the Coolify proxy on `localhost:80`, so **no tunnel or DNS change is needed** for `ea.bishnoi.ai`.

## What runs

| Service | Image | Reachable from | Data |
|---|---|---|---|
| `web` | `web/Dockerfile` (Next.js standalone, Node 22) | Coolify proxy → port 3000 (`ea.bishnoi.ai`) | none |
| `api` | `api/Dockerfile` (FastAPI, Python 3.14, local OCR) | private network only (`http://api:8000`) | volume `uploads` (documents, item photos) |
| `db` | `postgres:17-alpine` | private network only | volume `pgdata` |

- The browser only talks to `web`. `web` forwards `/api/*` to `api`, so cookies stay first-party and no CORS is needed.
- No host ports are published. Host port 8000 is the Coolify dashboard.

## One-time setup in Coolify

1. **Get the code to GitHub.** Coolify deploys from a Git repository.
   - The repo is kept small: `.gitignore` excludes `node_modules`, builds, local databases, uploads and the 16 MB of review screenshots. This matters because the server downloads from GitHub slowly.
2. **Create the resource.** In Coolify: Project → **+ New → Docker Compose** (build pack "Docker Compose"). Pick the repository and branch. Compose file: `/docker-compose.yml`.
3. **Set the domain.** On the `web` service, set the domain to **`http://ea.bishnoi.ai`**.
   - Use `http`, not `https`: Cloudflare terminates HTTPS and the tunnel reaches the proxy over plain HTTP. Users still see `https://`.
   - The port is 3000. Leave `api` and `db` without domains.
4. **Set the environment variables** from `.env.production.example`:
   - `SERVICE_PASSWORD_POSTGRES`: Coolify can generate it. Otherwise use 32+ letters and digits.
   - `BOOTSTRAP_ADMIN_EMAIL`, `BOOTSTRAP_ADMIN_NAME`, `BOOTSTRAP_ADMIN_PASSWORD`: the first Admin.
   - Leave the defaults unless there's a reason to change them. `PUBLIC_ORIGIN` must stay `https://ea.bishnoi.ai`.
5. **Deploy.** The first build takes several minutes: the API image installs the OCR engine and loads its models during the build. On first start the API:
   1. creates the tables;
   2. creates the starting data: companies GPI and 2MG, departments, the two approval routes, deadlines (SLA) and travel requirements;
   3. creates the first Admin.
6. **Backups.** In Coolify, enable **scheduled backups** for the Postgres data (daily). Also back up the `uploads` volume: documents and photos live there, not in the database.

## First sign-in

1. Open https://ea.bishnoi.ai and sign in with `BOOTSTRAP_ADMIN_EMAIL` / `BOOTSTRAP_ADMIN_PASSWORD`.
2. Choose a new password; the bootstrap password stops working.
3. Optionally clear `BOOTSTRAP_ADMIN_PASSWORD` in Coolify. It is never used again while an Admin with a password exists.
4. **Settings → People & access → Add person** for each user. Each gets a one-time temporary password to hand over privately; they choose their own at first sign-in.
5. **Settings → Approval routes**: assign the named approver stages:
   - Items: COO and Sir Naresh;
   - Concerns: Jasmine, Ma'am Mira and Ma'am Malhou.

   Until a stage is assigned, requests that reach it alert Admin instead of moving on.
6. **Settings → People & access**: turn on **Approval duties** for approvers, and set Assistants' delegations and company access.
7. **Settings → People & access → Departments**: add any missing departments (the starting list is Executive Admin, Operations, Sales, IT and Finance for GPI, and Operations for 2MG), and choose each **head**. Heads approve the "Department Head" step; choosing a head turns on their approval duties.

## Updating

Push to the deployed branch and press **Redeploy** in Coolify (or enable auto-deploy).

On start, the API adds any new tables and columns automatically (additive changes only). A future change that renames or removes a column will come with a written migration step.

## Security in production

- **Sign-in:**
  - email + password, hashed with scrypt;
  - the server-side session sits in an `HttpOnly; Secure; SameSite=Lax` cookie;
  - you're signed out after 12 hours idle, and after 14 days in any case;
  - an account locks for 15 minutes after 5 wrong passwords, and an address making many failed attempts is slowed down.
- **Requests that change data** are accepted only from `https://ea.bishnoi.ai`, which blocks cross-site forgery.
- **Development shortcuts are off:** the "Sign in as" directory, the `X-EA-User` header and the API docs.
- **Account changes:** deactivating a person, changing their user type or issuing a new password signs them out everywhere immediately.
- **Containers:** both run as non-root users, with security headers on every page.

## Known gaps (planned)

- **One Admin single sign-on.** It will replace passwords; accounts carry over.
- **Email notifications.** Zoho SMTP, because Gmail SMTP is blocked from this server's address. Notifications are in-app until then.
- **Alembic migrations.** Needed before the first non-additive schema change.

## Verified before deploy (13 Nov 2026, local)

- **API tests:** 89 pass on **Postgres 17**, the same version as the server, and on SQLite. The Postgres run found and fixed one real bug: row locks with joined data.
- **Production rehearsal:** API in production mode on an empty Postgres database, plus the standalone web build. 13 browser checks pass:
  - first Admin and forced password change;
  - departments and heads;
  - adding a person and their temporary password;
  - an employee's first sign-in on a phone;
  - sign out ends the session;
  - cookie flags;
  - blocked cross-site writes;
  - Admin-only endpoints refused.
- **Not yet run:** an actual Docker build. Docker isn't available on the development PC; the first build on the server is the check.
