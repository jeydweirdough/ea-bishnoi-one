# Product

<!-- impeccable:product-schema 1 -->

## Platform

web (installable PWA; used on both phone and desktop by every user type)

## Stack

Next.js (App Router) + TypeScript + Tailwind CSS frontend, shipped as a PWA (manifest + service worker). FastAPI backend, Postgres-ready for Neon (`DATABASE_URL`). Standalone repo for now; intended to move to `apps/executive-admin` in the Bishnoi One monorepo later.

## Users

- **Admin** — corporate-services operators with an operational overview of the companies they're authorized for. They assign, prioritize, resolve and close requests, and keep the registries current (assets, fleet, compliance, travel, contracts, banking).
- **Assistant** — operators who work the requests and registries assigned or delegated to them.
- **Employee** — self-service requestors. They raise concerns, request supplies and assets, track their own requests, and answer clarifications. They never see admin registries.
- Approvers (department heads, COO, named executives, Finance) act through separately granted workflow permissions that aren't tied to a user type.

Every user type switches between phone and desktop throughout the day.

## Product Purpose

Executive Admin is Bishnoi One's corporate-services application. It runs operational corporate administration: requests and concerns, assets, fleet and vehicles, corporate compliance, travel and immigration, lease contracts, and banking and cards. Success means every request has a visible owner, stage and due date, and no renewal (permits, registrations, visas, insurance, cards, leases) lapses unnoticed.

## Positioning

It's the one place where a staff concern or supply request moves from submission, through a configurable approval chain, to fulfillment with evidence. The same app also watches the company's renewal calendar. It's distinct from One Admin, which handles identities, roles, app access and security.

## Operating Context

- Approval templates (configurable, not universal): Request items go Employee → Approval Heads → COO → Sir Naresh → Admin/Assistant fulfillment. Staff concerns go Employee → Department Head → Jasmine → Ma'am Mira → Ma'am Malhou → Admin resolution.
- Finance/Books owns payments, fleet/RFID billing, card statements and reconciliation. People owns employee master data. One Admin owns login and app access.
- Companies include 2MG and Getmeds. Currency is PHP. Philippine government bodies: SEC/GIS, BOC, business permits.

## Capabilities and Constraints

- Phase 1: the app shell only. That's the persistent top bar, the collapsible nine-group Admin/Assistant sidebar, the simplified Employee self-service navigation, nested routes, active states, breadcrumbs and permission-aware navigation. **Every page shows Coming Soon.** No invented dashboards or production data.
- No Procurement navigation group. Procurement lives under Requests & Concerns.
- Never store CVV, PIN, full card numbers or banking credentials. Mask card references.
- Permission checks are enforced server-side. In Phase 1 the role is selected through a development role switcher until One Admin login is integrated.
- Later module order: employee requests → approvals and work queues → tasks/priorities → assets/receiving → fleet/finance → compliance/renewals → travel/immigration → contracts/banking → reports.

## Brand Commitments

Product family name: **Bishnoi One**. App name: **Executive Admin** (Corporate Services). No existing logo, palette or typeface. The visual identity is created fresh for this app.

## Evidence on Hand

Only the plan in `EXECUTIVE-ADMIN.md`. There's no real request data, metrics or user records. Don't fabricate counts or dashboards. Placeholders must read as Coming Soon.

## Product Principles

1. Status is never ambiguous: every record shows its owner, stage and next step.
2. Least privilege by default. Employees see only their own requests, and sensitive data stays hidden unless explicitly granted.
3. Approval power is separate from user type.
4. Renewals surface before they lapse.
5. Phone and desktop are equal citizens.

## Accessibility & Inclusion

WCAG 2.2 AA target. Touch targets of at least 44px on mobile. Fully keyboard-navigable sidebar.
