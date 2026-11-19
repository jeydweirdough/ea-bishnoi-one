# Phase 2 status

Plan: `EXECUTIVE-ADMIN.md` §27. **Phase 2 is complete** (12 Nov 2026): every sub-phase below is built, wired into the app, and verified end to end.

| Phase | Scope | Status |
|---|---|---|
| 2.1 | Employee requests | **Done**: review checkpoint 1 |
| 2.2 | Approvals & administration | **Done**: review checkpoint 1 |
| 2.3 | Assets | **Done**: review checkpoint 2 |
| 2.3a | Equipment Inventory (added to the plan 12 Nov 2026) | **Done**: Phase 2 completion |
| 2.4 | Fleet | **Done**: review checkpoint 2 |
| 2.5 | Compliance | **Done**: review checkpoint 3 |
| 2.6 | Travel & immigration | **Done**: review checkpoint 3 |
| 2.7 | Contracts & banking | **Done**: Phase 2 completion |
| 2.8 | Import & export | **Done**: Phase 2 completion |
| 2.9 | Documents & reports | **Done**: Phase 2 completion |

## Item photos from the phone camera (13 Nov 2026)

Assets, stock items and vehicles have photos, like a shop listing, so everyone knows exactly what an item looks like: staff when choosing what to issue, and employees when checking what was given to them.

**Taking photos**
- **Take photo** opens the phone's rear camera. **Upload** picks from the photo library or files.
- Available when registering an asset, adding a stock item or adding a vehicle, and on each record's page.
- Up to 8 photos per item. The first is the **main photo**. In the full-screen viewer (swipe or arrow keys), staff can **Make main photo** or **Remove**.

**Where photos show**
- The main photo is the thumbnail in the Asset Registry, Vehicles, Equipment Inventory and the employee's **My assets**, and in the record page header.
- The record page has a **Photos** gallery: top of the right column on desktop, before the history on phones.
- Photos are kept apart from **Files** (documents) and don't count toward the file limit.

**Other camera touchpoints**
- **Request form:** **Take photo** next to **Add a file**, so employees can show what they need or what is broken.
- **Documents on forms:** **Take photo** on phones, to photograph a permit, passport or OR/CR and attach it (nothing is read from it since 14 Nov).

**Privacy and size**
- Photos are shrunk on the phone before upload (long side 2000 px).
- The server re-encodes every photo: turned upright, long side 1600 px plus a 480 px thumbnail, with **all metadata removed (camera, time, GPS location)**.
- Non-image files and oversized images are refused.

**Access**
- Admin and Assistants add, change and remove photos.
- The holder of an asset can view its photos but not change them. Others can't see them.
- Adding, removing and changing the main photo are audited. Viewing a photo is not, because lists load many thumbnails and item photos are not sensitive.
- Card photos used for reading card details are still never stored.

**Verification:**
- `pytest` **83 passed**, including 4 new tests:
  - metadata stripped and photo turned upright;
  - main photo and promotion of the next one when it is removed;
  - the 8-photo limit;
  - holder can view but not change;
  - vehicle and stock photos.
- Browser suite **e2e7**: 14 checks.

## One place for each record: sub-menus merged (13 Nov 2026)

Several sub-menu screens only repeated what a record's own page already shows (e.g. a vehicle page shows its registration, insurance, PMS, fuel card and RFID). Each record now has one home. Fleet-wide views became filters on the main list instead of extra menu entries.

| Module | Sub-menu now | Merged into it |
|---|---|---|
| Assets | Asset Registry · Receiving Proof · Equipment Inventory | Assignment, Repairs → filters *Issued*, *Not yet acknowledged*, *Under repair*. Transfers → each asset's history. Repair updates moved onto the asset page. |
| Fleet | Vehicle Registry · Fuel & Toll Billing | Registration & Insurance, PMS → *Due soon* filter (Record renewal / Log PMS in the row). PMS & Repairs log → each vehicle's service history (Mark done is on the vehicle page). Fleet cards and RFID → *Fuel card & RFID* panel on the vehicle page. Default card limit and cards with no vehicle → Fuel & Toll Billing. |
| Compliance | Government Registrations · BOC Import / Export | SEC / GIS, Business Permits → type filters. Renewal Calendar → Home › Upcoming renewals (it already covered every module). Compliance Documents → each registration's or BOC case's files. |
| Travel | Flights · Hotels · Passports & Visas · Travel Requirements | Employee Visas, Expat Visas, Passport & Visa Renewals → filters *Passports*, *Employee visas*, *Expat visas*, *Expiring in 120 days*. |
| Contracts | Contract Registry · Monthly Rent · Lessors | Lease, Staff House → type filters. Renewals → *Ending in 120 days* filter; its rent section is now **Monthly Rent**. |
| Banking | Corporate Cards · Bank Requests | Card Renewals → *Expiring in 90 days* filter (Start renewal). Account Applications, Documentation, Finance Coordination → filters on **Bank Requests**. |

- **Old links still work.** Each merged screen's address opens its parent with the matching filter selected (e.g. `/fleet/registration-insurance` opens Vehicles › Due soon). Removed screens redirect: `/fleet/pms-repairs` → Vehicles, `/assets/transfers` → Asset Registry, `/compliance/renewal-calendar` → Home › Upcoming renewals, `/compliance/documents` → Registrations.
- **Notifications** now link to the record: low RFID balance → the vehicle; rent due → Monthly Rent.
- **Page headers:** one primary button. Import, Export and page settings are in the ⋯ *More actions* menu. On desktop the buttons sit top-right of the header.
- **Implementation:** `NavItem.under` marks a filtered view. `tabItems()` lists only real screens in the sub-menu and the group page. The screens still exist in search, so typing "RFID" or "SEC" lands on the right filter.

## Adding people who are not in the directory yet (13 Nov 2026)

Forms that name the person a record is about let staff add someone on the spot: a guest, a new hire not yet in One Admin, a consultant, or a family member. The last option in the person dropdown is **+ Add a person not in the list…**. It opens a short form below the field:
- First name, middle name, last name, suffix (Jr., Sr., II–V);
- Gender;
- Date of birth, or age when the date isn't known.

**Where it's available**
- Flight passenger
- Hotel guest
- Passport / visa holder
- Asset holder
- Stock "issue to"
- Vehicle driver
- Fleet card holder
- Corporate card custodian

It is **not** offered on staff roles (Responsible, Assignee, Officer, Approver). Those must be real staff.

**How it behaves**
- **Age:** stored as the date of birth, so it stays correct every year. If only the age is known, it's recorded with the day it was entered and keeps counting up.
- **Duplicates:** adding a name that already exists offers **Use the existing person** or **Add as a different person**.
- **Shown on forms:** once a person is chosen, the line under the field shows their gender and age, e.g. "Female · 35 years old". The flight PDFs print **Sex / Age** for the traveler.
- **Passports:** a scanned passport whose holder isn't in the list opens **Add a person** already filled with the holder's first, middle and last name, sex and date of birth, for review.
- **What added people can't do:**
  - They are marked **Added in Executive Admin**.
  - They can **never sign in** or approve.
  - They don't appear in "Sign in as" or in access grants, and they get no roles.
- **Directory sync:** when the One Admin directory is connected (Phase 3), added people can be merged with their directory records.
- **Development database:** new columns are added automatically at startup in development. Production schema changes will go through migrations.

**Verification:**
- `pytest` **79 passed**, including 6 new tests:
  - age from date of birth, and from age alone;
  - suffix;
  - duplicates and validation;
  - added people can't sign in and are hidden from sign-in and access lists;
  - employees can't add people;
  - the passport holder pre-fill;
  - sex and age on the flight PDF.
- Browser suite **e2e6**: 9 checks on desktop and phone.

## Document reading (OCR) — 13 Nov 2026 · removed 14 Nov 2026

> **Removed on 14 Nov 2026.** Reading was unreliable on real documents (the vehicle OR/CR in particular), so it was taken out rather than tuned per document. Forms now have **Attach the document** (camera, gallery or drag-and-drop): the file is saved with the record and the details are typed in. Fleet and corporate card forms have no photo box: their photos were only ever read and discarded, never stored. The OCR engine, `POST /api/v1/scan` and its tests are gone, and the API image no longer installs it. The notes below are kept as history.

Users upload the document and the system fills in the form. They review the values and save, and the file is attached to the record automatically.

| Form | What is read |
|---|---|
| Add registration, and Record renewal (Compliance) | Document name, type (SEC, GIS, Business Permit, Bureau of Customs, Fire, Pest Control), registration number, registered date, expiry |
| Add passport / visa (Travel) | Holder (matched to the employee directory), country, expiry, issue date, visa type. Only the **last 4** characters of the number. |
| Add contract, and Record renewal (Contracts) | Title, lessor (matched to the lessor list), start and end of term, monthly rent, deposit |
| Record registration / insurance renewal (Fleet) | New expiry date, OR or policy number, amount paid, insurer |
| Add vehicle, from the OR/CR (Fleet) | Plate, make, series, year model, color, body type, registered owner, registration expiry |
| Add fleet card, from a photo of the card (Fleet) | Last 4 digits, card holder (matched to an employee), vehicle (matched by plate), provider, fuel type |
| Add corporate card, from a photo of the card (Banking) | Bank, last 4 digits, expiry month and year, custodian (matched to an employee), card type |

**How it works**
- A PDF's own text layer is used when it has one. Scans, photos and image-only PDFs go through RapidOCR. Its ONNX models ship inside the Python package and run on this server, so documents are never sent to an outside service.
- Extraction is rule-based. Dates are found by their labels: issued, registered, valid until, expires, "from … to …". Numeric dates are read month-first (Philippine usage). For passports, the machine-readable zone is parsed when present.
- Every value carries a confidence score:
  - **Read from document** marks a confident value.
  - **Verify** marks anything below 80%.
  - Editing a value clears its marker.
  - The scan never overwrites what the user typed; default values can be replaced.
- If nothing can be read, the form says so and stays open for manual entry. The file is still attached.

**Safety**
- **Card photos are read and then discarded. They are never attached or stored**, because a card image shows the full number.
  - Only the last 4 digits leave the reader.
  - A card number that fails the checksum is marked **Verify**.
  - Security codes (CVV) are never read.
  - Corporate cards need the Banking grant.
- The scan endpoint (`POST /api/v1/scan`) saves nothing.
- Document text is never stored or logged. The audit trail records only which fields were read, never their values.
- Passports and visas need the travel-documents grant. Employees cannot scan.
- Accepted files: PDF, JPG, PNG and WebP, up to 10 MB, with the file signature checked.
- OCR runs one job at a time so it can't slow the rest of the API.

**Speed:** about 5 seconds per page on this laptop. PDFs with a text layer take under 1 second. The models load in the background when the API starts.

**Verification:** `pytest` **73 passed**, including 8 scan tests (with fleet card, corporate card and OR/CR):
- permit photo;
- SEC certificate PDF (text layer);
- passport matched to an employee, with only the last 4 characters kept;
- lease matched to a lessor;
- access, file-type and blank-file rules.

Browser suite **e2e5**: 17 checks on desktop and phone (now also the OR/CR, fleet card and corporate card). It covers registration, passport, lease and insurance renewal, attachment on save, and an unreadable file.

**Limits to know**
- Accuracy depends on the scan. Clear, upright photos read best; handwriting is not supported.
- Layouts that don't label their dates (no "issued" or "valid until") are given lower confidence and marked **Verify**.
- New document formats may need their label words added to `api/app/ocr.py`.

## Hardening against §28 / §29 (12 Nov 2026)

Tests for the remaining §29 items, in `api/tests/test_phase2_hardening.py`:

- **Large record sets**:
  - A 3,000-row Excel import is uploaded, checked and committed in one go.
  - Paging through all 3,000 stock lines returns every row exactly once, and page size is capped at 500.
  - Excel and CSV exports contain every row.
  - A file over the 5,000-row limit is refused before anything is written.
- **PDF page breaks**:
  - The 3,000-row PDF report runs to many pages. Every page says "Page X of Y" and repeats the column header, and no row is lost or duplicated at a break.
  - A 120-movement stock card, generated on both A4 and Letter:
    - has the correct paper size;
    - repeats the table header and shows the control number on every page after the first;
    - lists every movement exactly once;
    - keeps the signature block whole on the last page.
- **Import retries**:
  - If a row starts failing between the check and the commit (for example, someone registers the same serial meanwhile), the commit is refused and **nothing** is written.
  - You must re-check before committing again. Then you can import the good rows, and a repeated commit is a no-op.
  - Re-sending a corrected file in create-or-update mode adds the fixed rows and updates the rest, without duplicates.

**Bug found and fixed:** on the SQLite development database, a failed import commit still kept the rows saved before the failure, even though it reported "nothing was imported". This happened because the sqlite driver let each per-row savepoint commit on its own. `api/app/db.py` now opens a real transaction first, which is SQLAlchemy's documented setup. Postgres/Neon was not affected.

**Also fixed:** `api/requirements.txt` was missing `openpyxl` and `reportlab`, which import/export and PDFs need, so a fresh install would have failed. `pypdf` is added for the tests.

**Concurrent checklist ticks (fixed 12 Nov 2026):** clicking several bank requirements quickly could lose ticks. Two changes fix it:
- Checklist updates now lock the record while they write.
- On SQLite, write transactions queue instead of failing with "database is locked".

A test fires all ticks at once. It fails without the fix and passes with it.

**Verification:** `pytest` **65 passed**. Browser suites re-run on a fresh database: **26/26, 23/23, 19/19, 30/30**, with no errors in the API log.

## What works (2.3a, 2.7 – 2.9)

Sidebar: **Reports** joins the daily menu. **Contracts** and **Banking** join Registers. "Coming soon" is now empty, because every planned module is live.

**Equipment Inventory** (Assets › Equipment Inventory; tabs Stock, Requests to fill, Counts, Movements)

- **Stock lines**:
  - One line per item code and storage location, with on hand, reserved, available, reorder level/quantity, unit cost, supplier, and an "issue as asset" flag for serialized equipment.
  - The count strip shows lines, low stock, reserved units, and value of costed lines. Lines without a unit cost are never valued at ₱0.
- **Stock item page**:
  - Moves: Issue (to a person), Receive, Transfer to another location, Return, Adjust, and Write off.
  - Adjust is for Admin, or an Assistant granted **Inventory adjustments**. Write off is Admin only. Both need a reason.
  - Stock can never go negative or below what is reserved.
  - Every move is a line on the stock card, showing the running balance.
- **Requests to fill**:
  - Approved supply, asset and local-purchase requests are matched to stock lines.
  - Reserve holds the stock. Issue hands it over and notifies the requester. Release frees it.
  - "Draft restock request" turns low lines into a local-purchase draft.
- **Physical counts**:
  - Start a count for one location or all locations, enter the counted figures, and submit.
  - Admin (or a granted Assistant) posts the count, and the variances become logged adjustments.
- **Receiving Proof**: each delivered line now chooses **Register as assets**, **Add to stock** (pick the stock line) or **Neither**. A receipt can print its Asset Receiving Form.
- **Reminders**: low-stock alerts to Admins, once per threshold.

**Contracts** (tabs Lease Contracts, Staff House Contracts, Contract Registry, Renewals, Lessors)

- **Contracts**:
  - Fields: lessor, start/end, monthly rent, due day, deposit, notice period, responsible person, occupants (staff houses) and the Bishnoi One Contracts reference.
  - Status is computed automatically: Active, then For renewal inside the notice window, then Expired.
- **Renewal**: "Record renewal" creates a new contract linked to the old one, and marks the old one Renewed. Terminate is Admin only and needs a reason.
- **Monthly rent**:
  - "Prepare month" lists every active lease once (running it again is safe), then Send to Finance.
  - "Finance paid" needs Finance's payment reference. Cancel needs a reason.
- **Reminders**: contract end dates and rent due dates. Contract end dates also appear on the Renewal Calendar.

**Banking & Cards** (tabs Corporate Cards, Card Renewals, Account Applications, Documentation, Finance Coordination)

- **Access**: Admin only, or an Assistant whom an Admin grants **Banking** in Settings › People & access. Without it, the screens show "Restricted records" and the API returns 403. Views are audited.
- **Cards**:
  - Only the last 4 digits are stored. A full number is rejected, and notes that look like card numbers, CVVs, PINs or passwords are refused.
  - Each card records custodian, expiry, limit and status. "Start renewal" opens a renewal case.
- **Cases**:
  - Account applications start with the standard requirement checklist and can't be marked submitted until every item is ticked.
  - Flow: Submitted → Bank approved / Bank rejected (with reason) → Complete.
  - Finance steps: Send to Finance → Finance confirmed (reference) / Finance rejected. A case can't complete while Finance is pending.

**Import & export**

- **Import / Export buttons** sit on Requests, Tasks, Assets, Inventory, Vehicles, Fleet cards, Registrations, Contracts, Lessors, Corporate cards and Bank cases.
- **Import wizard**: Upload → Match columns → Check → Done.
  - **Excel template**: a Data sheet plus Instructions, Allowed values and Template info.
  - Accepts .xlsx and .csv.
  - Columns are matched automatically (exact names, synonyms, fuzzy matching). Uncertain matches are marked "please confirm".
  - Modes: create, update or upsert by a key column. Updates change only the mapped columns.
  - The check is a dry run. Rows with errors block the import unless you choose to skip them, and you can download an error report or an annotated copy of your file.
  - Formulas, macros and external links are never executed: formula cells are rejected.
  - A file that was already imported is detected. Imported requests arrive as drafts.
- **Exports**: Excel (typed columns, peso format, totals, Summary sheet), CSV or PDF, filtered by status, company and dates.
  - Cells that could run as formulas are neutralised.
  - Sensitive fields (passport/visa numbers, scans) are never exported.
  - Every export is audited.

**Documents & reports** (Reports in the sidebar; tabs Reports, Documents, Data imports)

- **Official documents**: 48 PDF templates, including request forms, PR/PO, memos, asset issuance/transfer/return/receiving forms, repair and vehicle job orders, fleet and RFID forms, compliance checklists, travel authorization, lease renewal, bank forms, the stock card, count sheets, issuance slips and monthly reports.
  - **Creating a form**: open the **Documents** panel on the record and choose Create. You can pick A4 or Letter.
  - **Control numbers**: each document gets one (`EA-PO-2026-0001`). Regenerating creates version 2 under the same number and supersedes the old version.
  - **Integrity**: each stored PDF carries a SHA-256 checksum that is verified on every download.
  - **Status comes from the real record, never claimed:**
    - Draft, For approval and Rejected carry a watermark.
    - **Approved** is used only when an approval was actually recorded: a request's approval route, or the bank's decision.
    - Complete records that have no approval step (stock cards, receipts, assignments, reports) are **Final**.
    - Approval lines are filled in only from recorded decisions. Signature lines stay blank.
  - **Lifecycle**: Issue is allowed only for Approved or Final documents. After that you can upload the signed copy. Only Admin can void.
  - **Employees** can create only the employee-facing forms, and only for their own requests.
- **Reports**: 46 reports across Requests, Assets, Inventory, Fleet, Compliance, Travel, Contracts and Administration.
  - Each report has date and company filters, totals, and Excel/CSV/PDF export.
  - Passport/visa reports need the travel-documents grant. Admin activity and audit reports are Admin only.
- **Executive Overview**: all §25 metrics from live records, shown as a count strip and a "Keep an eye on" list. The list covers renewals, expiring government documents, contracts for renewal, assets under repair, PMS due, low stock, trips being booked, active assets and tasks done this month. Assistants see "My work" (assigned requests and tasks, overdue items, waiting on Finance, renewals).

**Verification (12 Nov 2026)**
- `pytest`: **59 passed**. 20 are new for these sub-phases:
  - Inventory: moves and guards, reservations, counts, reorder, receiving into stock.
  - Contracts and banking: renewals, rent idempotency, banking grants, masking, the requirement and Finance gates.
  - Import/export: templates, import mapping, dry run, update merge, formula rejection, duplicate files, export neutralisation and sensitive-field exclusion.
  - Documents and reports: versioning, issue/sign/void, employee limits, the report catalogue and restrictions, and "Final, not Approved" for records with no approval step.
- Browser checks (Chrome, 390px phone and 1440px desktop) on a fresh database:
  - Inventory, Contracts, Banking, Import/Export, Documents & Reports: **30/30**
  - Compliance & Travel: **19/19**
  - Assets & Fleet: **23/23**
  - Requests & approvals: **26/26**
  - No console errors.
- `eslint` clean, `next build` passes (99 pages), and the Impeccable design detector reports no findings.
- Screenshots: `.impeccable/review/phase2d/`.

**Gaps to confirm**
- Starting lists to confirm: inventory categories, bank requirement checklists, document templates' wording, and the report list. Many come from the plan; some are reasonable defaults.
- Document PDFs use the company name and address from the directory seed. Logos and exact letterhead layouts should come from Bishnoi One branding.
- Rent and banking amounts are recorded for monitoring and Finance hand-off only; nothing posts to Finance's ledger.

## UX distill pass (12 Nov 2026)

Navigation is now task-first, with one "New request" entry point. Admin setup sits behind a single Settings door with tabs, and unbuilt modules are folded under "Coming soon". Forms ask for essentials first, with the rest under "More options". The rules are in `DESIGN.md` › Navigation and density. All nine groups and every route still exist and stay searchable; only the menus changed. Browser end-to-end re-run: 26/26 passed.

## What works (2.5 – 2.6)

Sidebar: Assets, Fleet, Compliance and Travel now sit under a **Registers** heading, apart from the daily work (Home, Requests, In approval, Tasks).

**Compliance** (six tabs)

- **Government Registrations**, plus filtered **SEC / GIS** and **Business Permits** views:
  - Types: Bureau of Customs, SEC, GIS, Business Permit, Pest Control, Fire Extinguishers, Other.
  - Expiry is computed from the registration date and years of validity, or entered directly.
  - An optional filing due date can't be after expiry.
  - Statuses Ongoing, For renewal, Completed, Expired, Terminated and Void. A record turns For renewal 60 days before its due/expiry date and Expired after expiry; this happens automatically.
- **Renewal**: "Record renewal" keeps a history (previous expiry, new dates, number, fees) and resets the status.
- **Assign renewal**: creates a linked task for the person filing it and makes them responsible.
- **Closing a record**: only Admin can terminate or void, with a reason. Closed records are read-only.
- **BOC Import / Export**:
  - Cases record direction, goods, BL/AWB, entry number, supplier/consignee, broker, route, ETA and assigned officer.
  - Milestones (Draft → Lodged → Assessment → Duties paid → Released → Delivered → Closed) only move forward, with notes, and form the submission history.
  - Cancelling needs a reason. Files can be attached.
- **Renewal Calendar**: permit/registration filing and expiry dates, customs ETAs, and vehicle registration/insurance dates on one timeline. Overdue items come first, then the rest grouped by month; you can view the next 3, 6 or 12 months.
- **Compliance Documents**: every file attached to registrations and BOC cases, searchable, each linking to its record. Downloads are permission-checked and audited.
- **Reminders**: Admins and the responsible person are warned at 60, 30, 7 and 0 days before a filing due date or expiry, and again while a record is overdue. Each warning is sent once.

**Travel & Immigration** (six tabs)

- **Flight Bookings**:
  - Domestic or international. International needs a destination country, and return can't be before departure.
  - Status flow: Requested → Booked (airline PNR required) → Ticketed → Completed, or Cancelled with a reason.
  - Each booking gets the **travel requirements** checklist for its type and destination, and **can't be ticketed until every item is checked**.
  - The passenger is notified when the flight is booked, ticketed or cancelled. Staff are reminded when a trip departs within 3 days without a ticket.
- **Hotel Reservations**:
  - Guest, hotel, city, check-in/out (at least one night), confirmation number (required to mark booked) and cost reference.
  - Can be linked to a trip.
- **Travel Requirements**:
  - Admin can add, edit and retire checklist items per travel type, for every destination or for a specific country.
  - Starting list: domestic — valid government ID with date of birth. International — passport valid 6+ months, visa/entry permit, return ticket, travel authorization.
  - These are starting values to confirm.
- **Employee Visas, Expat Visas, Passport & Visa Renewals**:
  - Records hold the visa type, country, application/issue/expiry/renewal dates, status and responsible person.
  - **Sensitive**: only the last 4 characters of a number are accepted and stored.
  - Visible to Admin, or to an Assistant only when an Admin switches on **Passports and visas** for them in Settings › People & access.
  - Every list and record view is written to the audit log. Edits log only which fields changed, never the values.
  - Status turns For renewal 90 days before expiry and Expired after expiry.
  - Reminders at 90, 30, 7 and 0 days go to Admins, the responsible person and the holder. The messages never include the number.
- **My travel** (employees): their trips, hotels, and passport/visa dates, read-only.

**Verification (12 Nov 2026)**
- `pytest`: **39 passed**. Nine are new: registration validation and auto status, the renewal and history rules, renewal assignment creating a task, terminate/void being Admin-only, de-duplicated expiry reminders including expired records, the BOC milestone order, calendar contents, compliance documents and access, flight validation, PNR and checklist-gated ticketing, configurable country requirements, hotels, and passport/visa masking, restriction, the access grant and audit (with no numbers in the log).
- Browser checks (Chrome, 390px phone and 1440px desktop), re-run on a fresh database: Compliance & Travel **19/19**, Assets & Fleet **23/23**, Requests & approvals **26/26**. No console errors.
- Screenshots: `.impeccable/review/phase2c/`.

**Gaps to confirm**
- Registration types, BOC milestones and the starting travel requirements are taken from the plan or are reasonable defaults. Confirm them, especially the visa rules per country, which change.
- Passport scans can be attached to a travel document, but routine exports (2.8) must exclude them.

## What works (2.3 – 2.4)

**Assets** (sidebar › Assets; the five screens are tabs)

- **Asset Registry**:
  - Register equipment with name, category, serial, brand/model, condition, location, department, quantity/unit, purchase date and reference, description, purpose and remarks.
  - Serial numbers are unique across the register (case-insensitive). A serialized record is always one unit.
  - Search by name, serial, tag or holder, with status chips and live counts.
- **Asset Assignment**:
  - Issue an asset to a person; their department follows them.
  - The holder is asked to acknowledge, from their Home page or **My assets**.
  - Staff can filter to "Not yet acknowledged".
  - A return records the condition.
- **Asset Transfers**: change holder, department and/or location, with a required reason. The tab is a movement log of issues, returns, transfers and acknowledgements.
- **Repairs**:
  - Send an asset for repair (it becomes Under repair and can't be issued).
  - Update provider and cost. Completing requires the condition after repair, and puts the asset back in stock or with its holder.
- **Receiving Proof**:
  - Approved item requests wait here until fully received.
  - Recording a delivery logs quantity, DR number and supplier, and can register the items as assets (one per serial, or one batch for non-serialized items).
  - Over-receiving is blocked.
  - The request shows "Partially received" or "Received" in its timeline, and the requester is notified.
- **Issuance documents**: a print-ready Asset Issuance Form (`/print/asset/:id`, A4) with letterhead, control number, asset table, acceptance text and blank signature lines. It states the in-app acknowledgement as a fact with its time, and never claims a signature.
- **Rules**:
  - Only Admin can retire an asset, and only after it's returned.
  - Retired assets are read-only.
  - Every change is in the asset history and the audit log.
- **Files**: attachments on assets.

**Fleet** (sidebar › Fleet; six tabs)

- **Vehicle Registry**:
  - Plate and conduction sticker are unique and normalised to upper case; at least one is required.
  - Records type, make/model/year, color, owner, assigned driver, registration/insurance/PMS dates, insurer and policy, odometer and status.
  - Only Admin can mark a vehicle as disposed.
- **Registration & Insurance**:
  - Everything due in the next 30, 60 or 120 days, soonest first, with overdue flagged.
  - "Record renewal" moves the date forward (it must be later than the current date) and keeps a renewal history with OR/policy number and amount.
- **PMS & Repairs**:
  - Log PMS, repairs or parts as done or scheduled, with cost, provider, odometer (can't go backwards) and next service date.
  - A done PMS updates the vehicle's next PMS date.
  - A scheduled repair puts the vehicle "In the shop" until marked done.
- **Shell Fleet Cards**:
  - Only the last 4 digits are accepted and stored; full card numbers are rejected.
  - Monthly limit defaults to ₱10,000, which Admin can change for new cards; each card keeps its own limit.
  - Records holder, vehicle, fuel type, billing cycle and active/suspended/cancelled status.
- **RFID Management**: Autosweep/Easytrip accounts with balance and a low-balance warning. "Request reload" sends a reload to Finance.
- **Fuel & Monthly Billing** (Finance hand-offs):
  - Card statements are recorded as drafts and sent to Finance. A card can have only one statement per month.
  - Finance paid needs Finance's payment reference. Rejected and Cancelled need a reason.
  - A paid RFID reload adds to the account balance.
  - Finance stays the source of truth; Executive Admin only records the hand-off and Finance's reference.
- **Reminders**: the 5-minute sweep warns Admins at 30, 7 and 0 days before a registration, insurance or PMS date, and when an RFID balance is low. Each warning is sent once per threshold.

**Access**
- Admin and Assistant work assets and fleet for the companies they can access.
- Employees see only assets issued to them, and are redirected away from the registries; the API also refuses them.
- A record in another company returns 404.

**Verification (12 Nov 2026)**
- `pytest`: **30 passed**. Ten are new for 2.3/2.4: serial uniqueness, the issue → acknowledge → return trail, transfer rules and cross-company denial, the repair state machine and retire rules, receiving limits, serial checks and auto-registration, plate uniqueness, renewal validation and de-duplicated reminders, service and odometer rules, card masking and default limit, Finance hand-off states, duplicate months and RFID balance.
- Browser checks, phone and desktop:
  - Assets & Fleet suite: **23/23 passed**.
  - Requests and approvals suite re-run: **26/26 passed**.
  - No console errors.
- Screenshots: `.impeccable/review/phase2b/`.

**Gaps to confirm**
- Asset categories, vehicle types, fuel types and RFID providers are starting lists in code. Making them editable comes with the field registry in 2.8.
- The `/print/asset/:id` page prints the asset's *current* condition. The stored, versioned forms are in the asset's Documents panel (2.9).
- Fleet costs are recorded for monitoring only; nothing posts to Finance's ledger.

## What works (2.1 – 2.2)

**Employee self-service** (`/me/*`)
- **Raise a Concern**:
  - Fields: category, subject, description, location, related asset, priority and needed-by date.
  - The requester block (employee ID, name, company, department, department head) fills automatically.
  - Concern categories Damaged equipment, Repairs and Maintenance go to the Repairs & Maintenance queue.
- **Request Supplies**:
  - Supplies, Equipment/asset or Local purchase, with any number of items (name, quantity, unit, category, brand, model, description).
  - Also asks for purpose, required date and delivery location.
- **Drafts, attachments and submission**:
  - Requests can be saved as drafts, then edited, submitted or deleted.
  - Evidence attachments upload with the request.
  - A per-form idempotency token means a retried submit never creates a duplicate.
  - The server validates every field, and errors show next to the field they belong to.
- **My Requests**: search, status groups, sorting and pagination.
- **Request page** (`/r/:id`):
  - A "what happens next" panel with the actions that apply right now.
  - Approval route, timeline, comments, attachments and a summary.
- **Requester actions**:
  - Withdraw (draft, submitted, under review or returned).
  - Answer a clarification by editing and resubmitting.
  - Confirm receipt or resolution, which closes the request.
- **Approvals & Status**: every request in approval, with stage progress.
- **Notifications**: unread badge in the top bar, unread filter, mark one or all read, deep links. The My Dashboard tiles use live counts.

**Approvals**
- **Workflow templates** (Administration › Approvals):
  - Ordered stages, each approved by the requester's department head or a named person who holds an approval grant.
  - Each stage has an on/off switch and an optional minimum priority, so a stage can apply only to High/Critical requests.
  - Each request type maps to one template.
  - Only Admin can edit templates. Assistants see them read-only.
- **Routes are snapshotted at submission**. Editing a template never rewrites requests already in flight.
- **Decisions**:
  - Approve (optional comment), Return for changes (reason required) or Reject (reason required).
  - Every decision is timestamped, kept in the history and written to the audit log.
- **Approval Inbox** (`/inbox`) lists pending stages, oldest first, with inline decisions and your recent decisions.
- **Delegation**:
  - An approver delegates to someone for a date range, and can revoke it.
  - Decisions record "on behalf of".
  - Delegation is the only way an Assistant gains approval power.
- **Separation of duties**:
  - Admin is not an approver unless granted.
  - The requester can never approve their own request; that stage is skipped and noted.
- **Missing approver**: when a department has no head, Admins are notified and can reassign the stage to anyone with an approval grant.

**Operations** (Admin and Assistant)
- **Executive Overview**:
  - Admin sees an operations overview: open, in approval, overdue and high/critical counts, unassigned approved work, the processing queue and their own tasks.
  - Assistants see "My work".
  - Figures from modules not built yet are not shown. Nothing is made up.
- **Request queues**:
  - All Requests plus one queue per type: Asset, Local purchase, Supplies, Repairs & Maintenance, Department concerns, Other.
  - Filters: overdue, due within 24h, assigned to me, unassigned.
- **Pending Approvals and Approval Tracking**: who holds each request, grouped by approver.
- **Priority Concerns**: overdue requests, plus open High and Critical ones.
- **Processing**:
  - Assign an owner (Admin, or an Assistant with the delegated right).
  - Set the effective priority, which recalculates the SLA deadlines.
  - Start processing, hand to Finance, record Finance's confirmation, mark fulfilled (note required), close, reopen, or cancel (Admin, reason required).
  - Staff can add internal notes the requester never sees.
- **Tasks**:
  - Create and assign tasks with a due date, priority and recurrence (daily, weekly or monthly).
  - Start, cancel, or complete with a required note and an optional evidence file.
  - Completing a recurring task creates the next one.
- **Priorities & SLA**:
  - Response and resolution targets per priority, a re-escalation interval, and a default owner by priority.
  - The overdue sweep runs every 5 minutes (`ESCALATION_INTERVAL_S`) and can also be run on demand.
  - Escalation notifies Admin and the owner once per level. Stalled approvals and due or overdue tasks send reminders.
- **Audit Logs**:
  - Append-only, with filters for type, reference and date range.
  - Covers request lifecycle events, approvals, assignments, priority changes, attachment uploads and downloads, task changes, workflow and SLA edits, access grants and escalations.
- **Settings** (access grants):
  - Approval duty per person.
  - For Assistants, the delegated rights to assign requests and set priority.
  - Company access per staff member.

## Security model

- **Every rule is enforced in the FastAPI service.**
  - Next.js `proxy.ts` only redirects navigation.
  - The UI shows only the actions the API returns in `actions`.
- **Identity comes from the server.** The development sign-in sends an employee number; role, approval grant, delegations and company access are read from the database. A tampered `ea_role` cookie only changes the menus, never the data.
- **Scope:**
  - An Employee sees only their own requests.
  - An Assistant sees their own requests plus requests assigned to them in companies they can access.
  - An Admin sees the companies they can access.
  - Approvers see requests routed to them.
  - A request outside your scope returns 404, so you can't tell whether it exists.
- **Attachments:**
  - Allow-listed types, with the file signature checked against the extension.
  - At most 10 MB per file and 10 files per record.
  - Stored under random keys.
  - Each download re-checks access, is audited, and is served with `no-store` and `nosniff`.
- **Concurrency:** request edits carry a `version`, and a stale edit gets 409. Document numbers come from row-locked sequences (`EA-REQ-2026-0001`, `EA-TSK-2026-0001`).

## Verification (12 Nov 2026)

- `api/`: `pytest`, **20 passed**. This covers:
  - creation, invalid submissions, duplicate tokens
  - employee isolation and cross-company denial
  - attachment type, size and access checks
  - the full approval chain, return and resubmit, reject
  - delegation, unauthorized and invalid decisions
  - assignment and priority delegation
  - workflow configuration validation
  - SLA escalation de-duplication
  - recurring tasks
  - the audit trail being append-only
- `web/`: `eslint` clean; `next build` passes (86 routes).
- **Browser end-to-end** (Chrome, 390px phone and 1440px desktop): **26/26 passed**. The run signs in, raises a concern with evidence on a phone, and submits a multi-item supply request with inline validation. The approver returns one request and approves another, and the employee resubmits. The 4-stage chain completes, and Admin assigns, processes and fulfils. A recurring task is created and completed. The employee confirms, notifications arrive, and Employees and Assistants are redirected away from staff-only and Admin-only pages. No console errors. Screenshots are in `.impeccable/review/phase2/`.

## Known gaps and decisions to confirm

- **Sign-in**: development directory only. One Admin integration is required before production; outside `ENV=development` the API refuses every request.
- **Directory data** (2 companies, 6 departments, 14 people) is placeholder seed data. Approver names (Jasmine, Mira, Malhou, Naresh) and a COO placeholder come from the plan. Real people, departments and heads must come from One Admin / People.
- **SLA hours** (Low 48/240, Normal 24/120, High 8/48, Critical 2/24) are starting values to confirm, editable in Priorities & SLA.
- **Database**:
  - Local development uses SQLite (`api/executive_admin.db`). Setting `DATABASE_URL` switches to Neon/Postgres.
  - Tables are created at startup in development; Alembic migrations should be added before the first Neon deployment.
  - The models have not yet been run against a real Neon instance.
- **Attachment storage** is the local disk (`api/uploads/`). Production needs object storage.
- **Not built yet:** email or push delivery of notifications; they are in-app only for now.

## Improvements, 14 Nov 2026

- **Automatic serial numbers.**
  - Every asset has a serial number. If none is typed, the system issues `<COMPANY>-<CATEGORY>-<NNNNN>`, for example `GPI-IT-00012`. Numbers never repeat.
  - Assets registered before this change got one on the next start.
  - Clearing a serial on edit keeps the current one.
- **Registering several of the same item** (fixes the quantity error).
  - Register asset asks "How many?". Five chairs become five records, each with its own serial, so each one can be issued, returned and repaired on its own.
  - Typed serials are used first, in order; the rest are numbered automatically.
  - Receiving Proof and Excel import work the same way.
- **Issuing several of the same item as one issuance.**
  - Issue asks "How many?" when identical items are in stock. Five clips to one person become one issuance (`EA-ISS-…`): one notification, one "Acknowledge all 5", and one Asset Issuance Form listing every serial.
  - The registry shows one row per issuance (e.g. "Paper clip box × 5", SN range) and one per set of identical items in stock; each row expands to its serials. Each item is still its own record, so one can be returned or repaired on its own.
  - Items issued one at a time before this change were grouped on start by person, item and day.
  - Serialized stock issued from Consumables & Stock is one issuance too.
- **Consumables are counted in pieces, not one record per piece.**
  - Register asks "How is it tracked?": Equipment (one record and serial per piece) or Consumable (counted in pieces). A consumable goes straight to Consumables & Stock as one stock line with its count, unit and storage location.
  - Items already registered per piece (e.g. clips) have "Move to Consumables & Stock" on the asset page: all their records become one stock line; pieces in stock become its balance and pieces with people are recorded as issued to them by quantity. Serial numbers are dropped; photos (duplicates kept once) and files move along. Items under repair or with a repair history stay assets.
  - The stock line is the one record for anything counted. Issuing from stock never creates asset records (the old "Register as an asset when issued" option is gone). Asset records it made earlier are folded back on start: pieces still with people stay as "issued" on the stock card; pieces that were returned through the asset page become a Return on the stock card (+1, from that person). Return on the stock card asks who brought it back.
  - Consumables are issued from the stock card by quantity ("3 pc to Linus Aurin"). The person sees them under My assets → Supplies issued to you.
- **Photo proof on every transaction, and every transaction opens.**
  - Every stock movement (receive, issue, use, return, transfer, adjust, write-off) and every asset action (issue, return, transfer, retire) can take up to 6 photos, in the form or later.
  - Tapping a stock card line or an asset history entry opens its details: when, who, to/from whom, quantity and balance, note, request, transfer location, reference, and the photos. Staff (and, for assets, the holder) can add photos there.
  - Take photo opens a full-screen in-app camera (several shots in a row, front/back switch). Each photo is stamped with the date, time (with time zone) and location (coordinates and accuracy) plus what it is for, burned into the picture. If the browser can't open the camera, the phone's camera app opens and the stamp is added after. Location is used only if the person allows it ("Location not shared" otherwise); the site's Permissions-Policy now allows camera and location for its own pages only.
  - The same facts are kept with each photo and shown under it (with a map link). Photos picked from the gallery are marked "Uploaded", never "Taken". Hidden photo metadata is still removed.
  - Return asks "Returned by" from the people who still have pieces of that item, with how many each has ("Carlo Diaz · has 6 pc"), or "Someone else…". A person can't return more than they have.
- **Registers as tables on desktop (Asset Registry, Consumables & Stock).**
  - Sortable columns (click a header: A to Z, click again: Z to A), a checkbox per row and "select all on this page", rows per page (10/25/50/100), and first / previous / next / last page. Clicking a row opens the record. Grouped asset rows ("× 5") expand to their serials in the table too. Columns that don't fit (Category, Condition) appear on wide screens only.
  - Selecting rows shows a bar with bulk actions. Assets: **Issue** (the selection goes to one person as one issuance: one acknowledgement, one issuance form, optional photo proof; only for items in stock), **Export** (just the selected records, Excel), **Move to Consumables & Stock**. Stock: **Export**, **Purchase request** (a draft for the selected lines).
  - Phones keep the card list; **Select** turns on checkboxes and the same bar sits above the tab bar.
  - API: `sort` and `dir` on `GET /assets` and `GET /inventory/items`; `POST /assets/issue` issues a selection as one issuance.
  - Forms now start with their prefilled values at once (no brief "Choose…" before the default appears).
- **One way to add files everywhere.** Every upload (photos, proof of receipt, request attachments, asset and request files, task evidence, signed copies, Excel import, document reading) uses the same box: drag and drop, paste a screenshot (Ctrl+V), Browse (gallery on a phone, file explorer on a computer), and Take photo on phones. Wrong file types are refused with a message.
- **Consumables & Stock** (formerly Equipment Inventory). This is where anything counted by quantity lives: bond paper, toner, coffee, cleaning supplies.
  - Item codes are automatic when left empty, for example `GPI-CS-0007`.
  - A new movement, **Record use**, covers consumables used in the office rather than handed to one person.
  - Every movement (in, issue, use, return, transfer, adjust, write-off) is on the item's stock card with the balance after it.
  - **Proof of receipt** (optional): when stock comes in (Receive, Return, or the opening quantity of a new item), up to 4 photos can be taken with the camera or picked from the gallery: the delivery, the DR or the receipt. They show as thumbnails on that line of the stock card and open full size. Like item photos, they are re-encoded with no camera or GPS data, and only staff can see them.
- **The request link: `/request`** (e.g. https://ea.bishnoi.ai/request). One link for everyone, to share in group chats.
  - It covers reporting a problem, requesting items, or both in one go, with up to 4 photos (cleaned of location data) and an urgent flag.
  - **Signed in:** their details are filled in, and the requests go straight into the usual approval route.
  - **Not signed in:** the person types their name, work email, mobile, company, department and position.
    - The submission waits in **Requests → From the Request Link**.
    - EA confirms who sent it: matched automatically by email, picked from the directory, or added as a new person. EA then accepts it, which files the real request(s) under that person and starts approval, or declines it with a reason.
    - The sender keeps a reference (`EA-WEB-2026-0001`) and can check its status with that reference and their email.
  - **Protection:** a limited number of submissions and status checks per connection; a hidden field that bots fill in; only the form's own fields are kept; photos are re-encoded; nothing reaches approvers before EA has checked it.
