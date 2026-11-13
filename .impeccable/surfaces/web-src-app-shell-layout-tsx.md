---
version: 1
slug: "web-src-app-shell-layout-tsx"
primary_target: "web/src/app/(shell)/layout.tsx"
related_targets: ["web/src/components/page/module-page.tsx"]
---

# Surface: Executive Admin app shell (all Phase 1 routes)

Scope: the persistent app shell, Admin/Assistant nine-group navigation, Employee self-service navigation, the approver inbox link, breadcrumbs, command palette, and the Coming Soon placeholder for every route. Mode: **Operate**.

Audience and job: Admins and Assistants work operational queues, mostly at desktops. Employees raise and track their own requests, mostly on phones. Every role uses both devices. In Phase 1 the job is to find any module in seconds and understand what each one will hold. Constraints: no invented data or dashboards, and every page reads Coming Soon. Installable PWA. WCAG 2.2 AA, with touch targets of 44px or more.

## Direction contract

THESIS: The Monochrome Product world, adopted by the user from the declined row. A near-monochrome operating sheet where the only color in the room means "you are here" or "this is live". It refuses the category default of a colored sidebar, gradient KPI cards and icon-tile grids.

OWN-WORLD: A neutral scale from #FAFAFA to #111111 with a cooler second layer (#F2F2F2) for the sidebar and top bar. One chartreuse accent (#A6C23F) is rationed to ring dots, the active-nav tick, the focus halo and the Coming Soon status ring. It's never text and never a fill behind text. Poppins is the single family, in Medium and SemiBold. Primary buttons are near-black #111 with a white label and an accent ring dot. Secondary buttons are ghost buttons with a one-pixel #CFCFCF hairline. Radius is 10px on panels and 8px on controls. Depth is a single soft offset shadow on floating layers only. Every divider is a one-pixel hairline. Every module carries a form code (EA-04.2) that the breadcrumbs, search and index share.

STORY: Users understand where they are (group, module, code), what this module will do and which fields it will hold, taken from the plan. They see that it's coming in a named build phase, so they believe the structure is real. Then they navigate to the next module, or open the palette with ⌘K or "/".

FIRST VIEWPORT (desktop 1440): A 56px top bar holds the wordmark "Bishnoi One / Executive Admin", the search trigger, a role switcher and an avatar. Below it, a 264px sidebar holds the nine groups as disclosure sections with an active tick, and collapses to a 64px icon rail. The content column has breadcrumbs, a 32px bold title with the code as meta beside it, a one-sentence purpose, and a Coming Soon status chip with an accent ring. Under that, a "Planned record" sheet shows the plan's real field names as a hairline ghost table. Mobile (390): the top bar holds the wordmark, search and menu. The bottom tab bar has 5 tabs for Employee, or Home / Requests / Assets / Renewals / More for staff. The groups open in a full-height sheet.

FORM: The Monochrome Product challenger, adopted. It ranked outside my grounded list; the user chose it over the assigned Receiving Stamp. Seed key ea35dda2. Signature interaction: a command palette that indexes all modules by name and code, with staggered result reveal and keyboard flow. Motion grammar: 160–220ms exponential ease-out on state changes only. The sidebar collapses with a width transition and labels cross-fade.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
