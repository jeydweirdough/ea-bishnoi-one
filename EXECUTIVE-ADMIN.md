
# Bishnoi One — Executive Admin
## Corporate Services Management System

**Status:** Phase 2 — Full Functional Development  
**Application:** Getmeds Executive Admin  
**Reference:** Zoho Creator, Zoho FSM, Zoho Expense, Zoho Contracts  
**Development:** Existing Next.js frontend and backend architecture  
**UI Authority:** Linus

---

# 1. PROJECT OVERVIEW

Executive Admin is the centralized Corporate Services Management System for Bishnoi One.

It manages company-wide administrative concerns, employee requests, assets, maintenance, vehicle monitoring, government registrations, travel, immigration, contracts, corporate cards, banking coordination, and administrative operations.

The application must support multiple companies, including Getmeds Philippines Inc. and 2MG, with company-specific records, access restrictions, and reporting.

The system must provide:

- Employee self-service
- Administrative operations
- Requests and concerns management
- Configurable approval workflows
- Asset management
- Maintenance and repair tracking
- Fleet and vehicle monitoring
- Government compliance monitoring
- Travel and immigration management
- Contract management
- Banking and corporate card coordination
- Task management
- Priority and SLA monitoring
- Notifications and reminders
- Excel and CSV import/export
- Field mapping and bulk operations
- PDF document generation
- Printable forms and signature workflows
- Operational dashboards
- Reports and analytics
- Audit trails

Executive Admin must remain separate from Bishnoi One's central One Admin application, which handles identities, organization access, and application permissions.

---

# 2. EXISTING APPLICATION

The application already contains:

- Sidebar navigation
- Top navigation
- Application search
- Breadcrumbs
- Module navigation
- Module descriptions
- Role visibility information
- Responsive layout
- Coming Soon pages
- Admin, Assistant, and Employee user types

The next development phase replaces Coming Soon pages with real interfaces and functional business logic.

## Development Requirements

1. Inspect existing source code before making changes.
2. Read `EXECUTIVE-ADMIN.md`, `DESIGN.md`, `PRODUCT.md`, and `README.md`.
3. Preserve existing working architecture.
4. Preserve existing navigation and visual consistency.
5. Replace placeholders with functional pages.
6. Connect records to a persistent database.
7. Implement complete business workflows.
8. Avoid recreating components that already work.
9. Follow existing coding standards.
10. Never claim functionality is complete without verification.

The existing standalone application must not be assumed to share the same architecture as the Bishnoi One V2 monorepo.

---

# 3. USER TYPES

The application supports three primary user types.

## 3.1 Admin

Admin manages authorized corporate administrative operations.

### Responsibilities

- View operational dashboards
- Manage company and department requests
- Monitor employee concerns
- Assign requests and tasks
- Configure priorities and SLA
- Manage asset records
- Manage asset assignments
- Track repairs and maintenance
- Manage vehicles
- Monitor fleet cards and RFID
- Maintain government registration records
- Monitor visa and passport renewals
- Coordinate flights and hotel bookings
- Monitor contracts and lease renewals
- Coordinate corporate cards and bank documentation
- Monitor Finance payment status
- Generate reports
- Import and export authorized records
- Generate official documents
- Maintain audit records
- Configure authorized system settings

Admin is not automatically an approver.

Approval permissions must be assigned independently.

## 3.2 Assistant

Assistant supports the daily administrative workload.

### Responsibilities

- View assigned tasks
- Process assigned requests
- Coordinate supplies
- Coordinate asset receiving
- Track repairs
- Monitor assigned vehicle records
- Track document renewals
- Follow up with departments
- Prepare documents
- Collect supporting attachments
- Prepare requests for approval
- Update assigned records
- Generate permitted reports
- Export authorized records
- Coordinate with Finance
- Update task progress

Assistant cannot automatically change system-wide policies or approve requests.

## 3.3 Employee

Employee is a self-service user who can raise concerns and submit requests.

### Responsibilities

- Submit concerns
- Request office supplies
- Request equipment or assets
- Report damaged equipment
- Request repairs
- Upload supporting attachments
- View own requests
- Track approval status
- Respond to clarification requests
- Withdraw eligible requests
- Receive notifications
- Confirm receipt of supplies
- Confirm resolution of concerns

Employees cannot access unrelated administrative records.

## 3.4 Permission Matrix

| Capability | Admin | Assistant | Employee |
|---|---|---|---|
| Operational dashboard | Yes | Assigned | No |
| Employee dashboard | Yes | Yes | Yes |
| Submit requests | Yes | Yes | Yes |
| View all authorized requests | Yes | Assigned | Own only |
| Assign requests | Yes | Delegated | No |
| Manage tasks | Yes | Assigned | No |
| Set effective priority | Yes | Delegated | No |
| Manage assets | Yes | Assigned | No |
| Manage vehicles | Yes | Assigned | No |
| Manage compliance records | Yes | Assigned | No |
| Manage travel records | Yes | Assigned | Own requests only |
| Manage contracts | Yes | Assigned | No |
| Manage banking records | Authorized | Restricted | No |
| Import records | Authorized | Delegated | No |
| Export records | Authorized | Restricted | Own permitted documents |
| Generate documents | Yes | Authorized | Own permitted forms |
| Configure workflows | Authorized | No | No |
| Approve requests | Explicit grant | Explicit delegation | Explicit grant only |
| Configure application | Authorized | No | No |

Permission enforcement must occur on the backend, not only through hidden UI controls.

---

# 4. EXECUTIVE ADMIN SIDEBAR

The existing nine navigation groups must be preserved.

## 4.1 Dashboard

- Executive Overview
- Pending Approvals
- Upcoming Renewals
- Priority Concerns

## 4.2 Requests & Concerns

- All Requests
- Asset Requests & Purchases
- Local Purchase Requests
- Office & Utility Supplies
- Repairs & Maintenance
- Department Concerns
- Other Requests
- Approval Tracking

## 4.3 Asset Management

- Asset Registry
- Asset Assignment
- Asset Transfers
- Repairs
- Receiving Proof
- Equipment Inventory

## 4.4 Fleet & Vehicles

- Vehicle Registry
- Registration & Insurance
- PMS & Repairs
- Shell Fleet Cards
- RFID Management
- Fuel & Monthly Billing

## 4.5 Corporate Compliance

- Government Registrations
- SEC / GIS
- Business Permits
- BOC Import / Export
- Renewal Calendar
- Compliance Documents

## 4.6 Travel & Immigration

- Flight Bookings
- Hotel Reservations
- Employee Visas
- Expat Visas
- Passport & Visa Renewals
- Travel Requirements

## 4.7 Contracts

- Lease Contracts
- Staff House Contracts
- Contract Registry
- Renewals
- Lessors

## 4.8 Banking & Cards

- Corporate Cards
- Credit Card Renewals
- Bank Account Applications
- Bank Documentation
- Finance Coordination

## 4.9 Administration

- Tasks
- Approvals
- Priorities & SLA
- Reports
- Audit Logs
- Settings

### Important Rule

Do not create a separate Procurement sidebar.

Asset purchases, local office purchases, Purchase Orders, and office supplies must remain under Requests & Concerns.

---

# 5. EMPLOYEE SELF-SERVICE

Employees must receive simplified navigation.

## Employee Sidebar

- My Dashboard
- Raise a Concern
- Request Supplies
- My Requests
- Approvals & Status
- Notifications

## 5.1 Raise a Concern

### Fields

- Request ID
- Employee ID
- Employee Name
- Company
- Department
- Department Head
- Concern Category
- Subject
- Description
- Location
- Related Asset
- Requested Priority
- Needed By
- Attachments
- Submission Date
- Status

### Functional Requirements

Employees must be able to:

1. Create a concern.
2. Save drafts.
3. Upload evidence.
4. Submit requests.
5. View request timelines.
6. Respond to clarification.
7. Withdraw eligible requests.
8. View decisions.
9. Confirm issue resolution.

## 5.2 Request Supplies

### Fields

- Request ID
- Employee
- Company
- Department
- Item Name
- Item Category
- Description
- Brand
- Model
- Quantity
- Unit
- Purpose
- Required Date
- Delivery Location
- Priority
- Attachments
- Approval Status
- Fulfillment Status

Support multiple items within one request.

Employees cannot directly approve purchases or confirm Finance payments.

---

# 6. APPROVAL WORKFLOWS

Approval workflows must be configurable.

## 6.1 Item Request Approval

Employee / Requestor
→ Approval Heads
→ COO
→ Sir Naresh
→ Executive Admin Processing
→ Purchase / Fulfillment
→ Receiving
→ Issuance
→ Completed

## 6.2 Staff Concern Approval

Staff
→ Department Head
→ Jasmine
→ Ma'am Mira
→ Ma'am Malhou
→ Executive Admin Processing
→ Resolution
→ Completed

These represent configurable workflow templates.

Not every request must use every approval stage.

## 6.3 Approval Features

- Configurable approval chains
- Multiple approval levels
- Assigned approvers
- Approval delegation
- Approval comments
- Rejection reasons
- Return for correction
- Resubmission
- Approval notifications
- Escalations
- Approval timestamps
- Approval history
- Audit trails

Approval permissions must remain separate from CRUD permissions.

---

# 7. REQUESTS & CONCERNS

This module manages administrative requests from all departments.

## Categories

- Asset Requests
- Equipment Purchases
- Local Purchases
- Office Supplies
- Utility Supplies
- Repairs
- Maintenance
- Department Concerns
- Other Requests

## Functional Requirements

- Create requests
- Assign request owners
- Configure priorities
- Attach documents
- Submit requests for approval
- Track approval progress
- Record procurement-related details
- Generate Purchase Orders where applicable
- Track receiving
- Track issuance
- Confirm fulfillment
- Close requests
- Generate reports

### Request Statuses

- Draft
- Submitted
- Under Review
- Returned for Revision
- Approved
- Rejected
- In Progress
- Awaiting Finance
- Fulfilled
- Closed
- Cancelled

All status transitions must follow explicit business rules.

---

# 8. ASSET MANAGEMENT

Manage company-owned equipment and physical assets.

## Asset Fields

- Asset ID
- Asset Name
- Category
- Serial Number
- Brand
- Model
- Company
- Department
- Quantity
- Unit
- Issued By
- Issued To
- Date Issued
- Purchase Date
- Purchase Reference
- Description
- Purpose
- Condition
- Status
- Location
- Attachments
- Proof of Receiving
- Remarks

## Asset Conditions

- Brand New
- Used
- For Repair
- Damaged
- Unserviceable

## Functional Requirements

- Asset registration
- Asset assignment
- Asset transfer
- Asset receiving
- Asset returns
- Asset replacement
- Repair history
- Ownership tracking
- Issuance acknowledgment
- Receiving documents
- Asset register reports

Serialized physical assets should have unique serial numbers and individual records.

## 8.1 Equipment Inventory

Track stock on hand for equipment and supplies kept in storage: spare laptops, monitors, peripherals, tools, furniture, and office and utility supplies.

The Asset Registry holds one record per serialized item issued to a person. Equipment Inventory holds counted quantities per storage location. An inventory item that is issued as a serialized asset is registered in the Asset Registry at the moment of issuance.

### Inventory Item Fields

- Item Code (SKU)
- Item Name
- Category (Equipment / Supplies / Spare Parts / Consumables)
- Brand
- Model
- Unit
- Company
- Storage Location
- Quantity on Hand
- Reserved Quantity
- Available Quantity
- Reorder Level
- Reorder Quantity
- Unit Cost (PHP)
- Preferred Supplier
- Serialized on Issue (Yes / No)
- Last Counted Date
- Status (Active / Discontinued)
- Remarks
- Attachments

### Stock Movements

- Stock In (receiving, linked to Receiving Proof or a purchase reference)
- Issue (to an employee or department, linked to the supply or asset request where applicable)
- Transfer between storage locations
- Return to Stock
- Adjustment (count correction; reason required)
- Write-off (damaged, lost or expired; Admin only; reason required)

Every movement records quantity, from/to location, related request or receipt, actor, timestamp and remarks.

### Functional Requirements

- Stock levels by item, location and company
- Available = on hand − reserved
- Reserve stock against approved supply requests
- Issue stock from approved supply requests and deduct automatically
- Add stock automatically when deliveries are recorded in Receiving Proof
- Register serialized items as assets on issuance
- Low-stock alerts when available quantity falls to the reorder level
- Reorder suggestion that drafts a Local Purchase or Asset Request
- Physical inventory counts (full or by location) with count sheets, variance review and approved adjustments
- Movement history per item
- Inventory valuation (quantity × unit cost)
- Stock card per item

### Rules

- Stock can never go negative.
- Issuance cannot exceed available quantity.
- Adjustments and write-offs require a reason and are audited.
- Write-offs and count adjustments above a configurable threshold require Admin approval.
- Historical movements are never edited; corrections are new movements.

### Permissions

| Capability | Admin | Assistant | Employee |
|---|---|---|---|
| View inventory | Yes | Assigned locations | No |
| Stock in / issue / transfer | Yes | Assigned locations | No |
| Adjust counts | Yes | Delegated | No |
| Write off stock | Yes | No | No |
| Configure items and reorder levels | Yes | Delegated | No |

Employees request items through Request Supplies; they do not see inventory records.

---

# 9. FLEET & VEHICLES

## 9.1 Vehicle Registry

### Fields

- Vehicle ID
- Company
- Vehicle Type
- Make
- Model
- Year Model
- Color
- Plate Number
- Conduction Sticker
- Owner Name
- Assigned Driver
- Registration Renewal Date
- Insurance Expiry Date
- Next PMS Date
- Fleet Card
- RFID Accounts
- Status
- Attachments

## 9.2 Vehicle Maintenance

Track:

- Preventive maintenance
- Repair requests
- Repair history
- Parts replacement
- Repair costs
- Service providers
- Next service date
- Maintenance attachments

## 9.3 Shell Fleet Card

### Fields

- Fleet Card ID
- Company
- Vehicle ID
- Plate Number
- Conduction Sticker
- Vehicle Model
- Fuel Type
- Assigned User
- Card Reference
- Configured Amount
- Billing Cycle
- Finance Reference
- Payment Status
- Monitoring Status

Use PHP 10,000 as an initial configurable example amount.

Do not hardcode this as a universal limit.

## 9.4 RFID

Track:

- Vehicle
- RFID Provider
- RFID Account
- Payment Request
- Finance Payment Status
- Reload History
- Available Balance
- Monitoring Status

## Finance Workflow

Fleet / RFID Request
→ Executive Admin
→ Finance Payment
→ Payment Confirmation
→ Executive Admin Monitoring

Finance remains the source of truth for payments.

---

# 10. CORPORATE COMPLIANCE

Manage government documents and regulatory renewals.

## Registration Types

- Bureau of Customs
- SEC
- GIS
- Business Permits
- Pest Control
- Fire Extinguishers
- Other Government Registrations

## Fields

- Document ID
- Document Name
- Registration Type
- Registration Number
- Company
- Registration Date
- Years of Validity
- Expiry Date
- Due Date
- Responsible Employee
- Attachments
- Status
- Notes
- Renewal History

## Statuses

- Ongoing
- Completed
- For Renewal
- Expired
- Terminated
- Void

## Functional Requirements

- Registration tracking
- Renewal tracking
- Expiry notifications
- Document attachments
- Filing history
- Renewal assignments
- Compliance reports
- Audit history

## BOC Import / Export

Support:

- Importation records
- Exportation records
- Shipment references
- Customs documentation
- Processing milestones
- Assigned officers
- Submission history
- Attachments
- Status monitoring

---

# 11. TRAVEL & IMMIGRATION

## Flight Bookings

### Fields

- Booking ID
- Booking Reference Number
- Employee / Passenger
- Company
- Department
- Travel Type
- Origin
- Destination
- Departure Date
- Return Date
- Airline
- Booking Status
- Attachments
- Notes

### Requirements

Domestic flights may require an accepted valid ID with date of birth.

International travel may require a passport and additional destination-specific documentation.

Requirements should be configurable, not universally assumed.

## Hotel Reservations

Track:

- Hotel
- Guest
- Destination
- Check-in
- Check-out
- Booking Reference
- Booking Status
- Cost Reference
- Attachments

## Visas

Support employee and expat visa records.

### Fields

- Employee ID
- Visa Type
- Country
- Application Date
- Expiry Date
- Renewal Date
- Application Status
- Responsible Employee
- Supporting Documents
- Notes

Passport and visa information must be treated as sensitive personal data.

---

# 12. CONTRACT MANAGEMENT

## Contract Categories

- Office Lease
- Staff House Lease
- Other Corporate Contracts

## Fields

- Contract ID
- Contract Type
- Company
- Property
- Location
- Lessor Name
- Start Date
- End Date
- Covered Year
- Monthly Rental
- Renewal Date
- Due Date
- Status
- Documents
- Notes

## Functional Requirements

- Contract registry
- Contract monitoring
- Renewal reminders
- Rental monitoring
- Document attachments
- Contract history
- Renewal reports

Avoid duplicating authoritative contracts already managed in Bishnoi One Contracts.

---

# 13. BANKING & CORPORATE CARDS

Manage administrative coordination for:

- Corporate Credit Cards
- Credit Card Renewals
- Bank Account Applications
- Bank Account Documentation
- Bank Renewals
- Finance Coordination

## Fields

- Case ID
- Company
- Bank
- Request Type
- Account / Card Reference
- Responsible Employee
- Application Date
- Renewal Date
- Requirements
- Attachments
- Finance Status
- Notes

Never store CVV, PINs, online-banking passwords, or unnecessary complete card numbers.

Actual banking transactions and financial records remain under Finance.

---

# 14. ADMINISTRATION

## Tasks

- Task creation
- Assignment
- Due dates
- Status tracking
- Recurring tasks
- Related module records
- Completion evidence

## Priorities

- Low
- Normal
- High
- Critical

## SLA

- Response deadlines
- Resolution deadlines
- Overdue monitoring
- Escalation rules
- Priority-based assignment

## Notifications

- New request
- Approval required
- Approval decision
- Task assignment
- Due date reminder
- Overdue notice
- Renewal warning
- Payment status update
- Fulfillment confirmation

---

# 15. EXCEL AND CSV IMPORT SYSTEM

Every applicable module must support importing records.

## Supported Formats

- XLSX
- CSV

Do not execute workbook macros, formulas, or external links.

## Import Workflow

1. Select module.
2. Download official Excel template or upload existing file.
3. Select worksheet.
4. Detect column headers.
5. Preview uploaded data.
6. Automatically suggest field mapping.
7. Allow manual mapping corrections.
8. Validate records.
9. Detect duplicates.
10. Display errors and warnings.
11. Preview create/update operations.
12. Confirm import.
13. Process records.
14. Display results.
15. Download an error report if needed.

## Automatic Field Mapping

The system must recognize common field-name variations.

Example:

| Uploaded Column | System Field |
|---|---|
| Employee Name | employee_name |
| Employee ID | employee_id |
| Department | department_code |
| Company | company_code |
| Serial No. | serial_number |
| Brand Name | brand |
| Model Name | model |
| Date Issued | issued_date |
| Renewal Date | renewal_date |
| Plate No. | plate_number |

Field mapping must use stable internal identifiers.

Ambiguous mappings require user confirmation.

## Import Validation

Validate:

- Required fields
- Data types
- Duplicate records
- Invalid dates
- Missing relationships
- Invalid employee IDs
- Invalid company codes
- Invalid departments
- Invalid quantities
- Invalid currency values
- Invalid status values
- Unauthorized updates

## Import Error Report

Include:

- Worksheet
- Row Number
- Column
- Original Value
- Error Description
- Expected Value
- Suggested Correction

Allow downloading corrected or annotated workbooks.

## Import Modes

- Create New
- Update Existing
- Create or Update

Updates must use stable record IDs or explicitly approved matching keys.

Prevent normal imports from overwriting:

- Approval decisions
- Audit history
- Signatures
- Payment confirmations
- Protected workflow states
- Restricted personal information

## Import Security

- Server-side authorization
- File size limits
- File validation
- Import audit logs
- Transaction-safe processing
- Duplicate protection
- Idempotent retry handling
- Company-level isolation

---

# 16. EXCEL TEMPLATE GENERATION

Every importable module must provide a downloadable template.

## Template Requirements

Each template should contain:

1. Data entry worksheet
2. Field instructions worksheet
3. Allowed values worksheet where applicable
4. Sample records
5. Required field indicators
6. Data type instructions
7. Template version metadata

## Canonical Template Fields

### Employee Requests

- request_id
- request_type
- company_code
- department_code
- requester_employee_id
- subject
- description
- priority
- needed_by_date
- assigned_employee_id
- status

### Supply Requests

- request_reference
- company_code
- department_code
- requester_employee_id
- item_name
- quantity
- unit
- purpose
- needed_by_date
- priority

### Asset Registry

- asset_id
- company_code
- asset_category
- brand
- model
- serial_number
- condition
- status
- department_code
- issued_by_employee_id
- issued_to_employee_id
- quantity
- purpose
- receiving_reference

### Equipment Inventory

- item_code
- company_code
- item_name
- category
- brand
- model
- unit
- storage_location
- quantity_on_hand
- reorder_level
- reorder_quantity
- unit_cost_php
- preferred_supplier
- serialized_on_issue
- status

Stock movements import on a separate worksheet linked by item_code (movement_type, quantity, from_location, to_location, reference, remarks).

### Vehicle Registry

- vehicle_id
- company_code
- vehicle_type
- make
- model
- year_model
- plate_number
- conduction_sticker
- color
- owner_name
- registration_renewal_date
- insurance_expiry_date
- next_pms_date

### Fleet Card / RFID

- company_code
- vehicle_id
- account_type
- provider
- account_reference
- fuel_type
- configured_limit_php
- billing_cycle
- finance_reference
- monitoring_status

### Government Registrations

- company_code
- document_name
- registration_type
- registration_number
- registration_date
- validity_years
- due_date
- status
- notes
- document_reference

### Travel and Visa

- company_code
- employee_id
- record_type
- booking_reference
- travel_date
- destination
- passport_expiry_date
- visa_expiry_date
- status

Sensitive fields must be excluded from routine exports.

### Contracts

- company_code
- contract_reference
- contract_type
- lessor_name
- start_date
- end_date
- monthly_rent_php
- renewal_due_date
- status
- site

### Banking Coordination

- company_code
- case_reference
- case_type
- bank_name
- request_subject
- masked_card_last4
- renewal_date
- finance_reference
- status

### Tasks

- company_code
- task_title
- assigned_employee_id
- due_date
- priority
- source_module
- source_record_id
- status
- notes

These are planned canonical fields. Reconcile them with the actual database schema before implementation.

Multi-item requests and document relationships should use separate child worksheets linked by stable IDs.

---

# 17. EXPORT SYSTEM

Every applicable module must support authorized exports.

## Formats

- Excel (.xlsx)
- CSV (.csv)
- PDF (.pdf)

## Export Options

- Export selected records
- Export filtered records
- Export current page
- Export all authorized records
- Export by company
- Export by department
- Export by date range
- Export by status
- Export by assigned employee

## Excel Export Requirements

- Proper column headers
- Formatted tables
- Date formatting
- PHP currency formatting
- Typed numeric values
- Totals
- Summary worksheet where appropriate
- Record count
- Applied filter information
- Generated date
- Generated by
- Company name

Exports must preserve correct data types.

## CSV Export Requirements

- UTF-8 encoding
- Proper delimiter handling
- Escaped quoted values
- Safe handling of leading zeros
- Protection against spreadsheet formula injection

## Export Security

- Permission-controlled downloads
- Company-scoped exports
- Column-level restrictions
- Sensitive information masking
- Download audit logs
- Restricted attachment access
- Secure temporary download links where appropriate

---

# 18. REPORT GENERATION

Every applicable module must provide functional reports.

## Standard Reports

### Requests

- Request Register
- Pending Requests
- Approval Aging
- Requests by Department
- Requests by Company
- Priority Concerns
- Supply Requests
- Fulfillment Reports

### Assets

- Asset Registry
- Asset Assignment
- Asset Transfer
- Asset Repair
- Asset Receiving
- Unreturned Assets

### Equipment Inventory

- Stock on Hand
- Low Stock / Reorder Report
- Stock Movement Report
- Inventory Valuation
- Inventory Count Variance
- Issuance by Department

### Fleet

- Vehicle Registry
- PMS Due Report
- Insurance Expiry Report
- Vehicle Registration Renewal
- Fleet Card Monitoring
- RFID Payment Monitoring
- Repair History

### Compliance

- Government Registration Report
- Expiring Documents
- Renewal Calendar
- SEC / GIS Monitoring
- Business Permit Monitoring
- BOC Case Reports

### Travel

- Flight Booking Report
- Hotel Reservation Report
- Employee Travel Report
- Visa Expiry Report
- Passport Renewal Report

### Contracts

- Contract Register
- Lease Renewal Report
- Monthly Rental Summary
- Expiring Contracts

### Administration

- Assigned Tasks
- Overdue Tasks
- SLA Performance
- Approval History
- Administrative Activity Report
- Audit Report

Reports must use real database records and enforce authorized access.

---

# 19. PDF DOCUMENT GENERATION

Build a reusable, centralized document generation engine.

## Supported Outputs

- Excel reports
- CSV reports
- PDF reports
- Printable forms
- Signature-ready PDFs
- Approval documents
- Official corporate forms

## PDF Design Reference

Use the supplied Bishnoi One quotation document as a reference for document structure and print quality.

Its relevant design characteristics include:

- Company letterhead
- Company address
- Bold document title
- Control number
- Issue date
- Structured information sections
- Tables
- Totals where applicable
- Certification text
- Authorized representative information
- Signature sections
- Footer
- Page numbering

Do not reuse quotation-specific medical or patient fields in Executive Admin documents.

## Document Layout Requirements

Each generated document should support:

1. Company letterhead
2. Company name
3. Company address
4. Document title
5. Document control number
6. Document issue date
7. Reference number
8. Requestor / department
9. Relevant record information
10. Itemized table where appropriate
11. Amount and totals where applicable
12. Remarks / justification
13. Approval status
14. Signature sections
15. Footer
16. Page numbering

## Print Requirements

- A4 paper support
- Letter paper support
- Consistent margins
- Clear typography
- Proper table alignment
- Automatic page breaks
- Repeated headers for multipage tables
- No clipped content
- Print preview
- Browser printing

---

# 20. OFFICIAL DOCUMENT TEMPLATES

Implement document templates for:

## Requests and Purchases

- Supply Request Form
- Asset Request Form
- Purchase Request
- Purchase Order
- Local Purchase Request
- Request Approval Memo

## Assets

- Asset Issuance Form
- Asset Receiving Form
- Asset Transfer Form
- Asset Return Form
- Asset Turnover Acknowledgment
- Equipment Repair Request

## Equipment Inventory

- Stock Card
- Inventory Count Sheet
- Inventory Issuance Slip
- Stock Adjustment / Write-off Form

## Maintenance

- Maintenance Job Order
- Repair Authorization
- Maintenance Completion Report
- Service Receiving Form

## Fleet

- Vehicle Assignment Form
- Vehicle Maintenance Request
- Fleet Card Request
- RFID Payment Request
- Vehicle Renewal Checklist

## Corporate Compliance

- Registration Renewal Request
- Government Document Checklist
- Compliance Monitoring Report
- BOC Document Checklist

## Travel

- Travel Authorization
- Flight Booking Summary
- Hotel Booking Summary
- Visa Requirements Checklist
- Travel Approval Memo

## Contracts

- Lease Renewal Request
- Contract Monitoring Report
- Contract Renewal Memo

## Banking

- Corporate Card Request
- Bank Account Application Checklist
- Credit Card Renewal Request
- Banking Documentation Request

## Administration

- Task Completion Report
- Employee Concern Resolution Form
- Monthly Administrative Report
- Executive Summary Report

---

# 21. SIGNATURE SYSTEM

Generated official documents must support signature fields.

## Signature Sections

- Prepared By
- Checked By
- Reviewed By
- Recommended By
- Approved By
- Received By
- Acknowledged By

Use only the roles appropriate to each document.

## Signature Requirements

- Signatory name
- Designation
- Department
- Signature placeholder
- Signature date
- Approval reference
- Document control number

## Document States

- Draft
- For Review
- For Approval
- Approved
- Rejected
- Issued
- Signed
- Superseded
- Voided

A generated PDF must not claim approval or signature unless the required event has actually occurred.

## Electronic Signatures

If electronic signing is authorized and implemented:

- Verify signer identity.
- Capture consent.
- Record signing timestamps.
- Preserve document integrity.
- Maintain audit history.
- Protect issued documents against silent alteration.

Typed names and uploaded signature images must not automatically be treated as legally verified electronic signatures.

Signed document versions must remain traceable and immutable.

---

# 22. DOCUMENT CONTROL

Every official document requires a unique reference.

## Example Numbering Formats

- EA-REQ-2026-0001
- EA-PO-2026-0001
- EA-AST-2026-0001
- EA-INV-2026-0001
- EA-MNT-2026-0001
- EA-FLT-2026-0001
- EA-CMP-2026-0001
- EA-TRV-2026-0001
- EA-CON-2026-0001

These are proposed numbering conventions.

The implementation must support configurable document types and sequences.

## Document Control Requirements

- Unique reference number
- Version number
- Generated timestamp
- Generated by
- Related record
- Company
- Status
- Approval record
- Signature status
- Document history
- Download history

Issued documents must not be silently overwritten.

Amendments must create traceable revisions.

---

# 23. DATABASE AND BACKEND REQUIREMENTS

Use the existing database and backend architecture.

Inspect the actual project before creating migrations.

## Core Data Domains

- Companies
- Departments
- Employees
- User permissions
- Requests
- Request line items
- Concerns
- Approval workflows
- Approval decisions
- Tasks
- Assets
- Asset assignments
- Asset transfers
- Asset maintenance
- Inventory items
- Inventory stock movements
- Inventory counts
- Vehicles
- Fleet cards
- RFID accounts
- Government registrations
- Renewal records
- Travel bookings
- Visa records
- Contracts
- Banking coordination
- Attachments
- Notifications
- Import jobs
- Export jobs
- Field mapping presets
- Document templates
- Generated documents
- Signatures
- Audit events

## Backend Requirements

- Server-side validation
- Authenticated requests
- Role- and scope-based authorization
- Company isolation
- Transaction-safe writes
- Unique constraints
- Referential integrity
- State transition validation
- Attachment security
- Audit logging
- Pagination
- Filtering
- Search
- Proper error handling
- Safe bulk operations

Do not duplicate authoritative records from connected Bishnoi One systems.

---

# 24. IMPORT/EXPORT ARCHITECTURE

Build one reusable import/export engine rather than separate implementations for every page.

## Components

### Field Schema Registry

Defines:

- Canonical field name
- Display label
- Data type
- Required or optional
- Accepted values
- Importable status
- Exportable status
- Privacy classification
- Relationship rules
- Validation rules

### Template Generator

Creates standardized Excel templates from module schemas.

### Mapping Engine

Maps uploaded columns to canonical system fields.

### Validation Engine

Validates uploaded records before database writes.

### Import Processor

Handles:

- Batch processing
- Create/update/upsert
- Duplicate detection
- Transaction handling
- Import history
- Error reports

### Export Processor

Creates:

- XLSX
- CSV
- PDF

### Document Engine

Creates formal reports, approval forms, printable documents, and signature-ready PDFs.

## UI Actions

Provide the following where relevant:

- Import Data
- Download Template
- Map Fields
- Validate Import
- Confirm Import
- View Import Results
- Download Errors
- Export Data
- Generate Report
- Generate Document
- Print Preview
- Download PDF
- Send for Approval
- View Signature Status

These actions must work, not be decorative controls.

---

# 25. REPORTING AND DASHBOARDS

Replace placeholder dashboards with database-backed metrics.

## Executive Dashboard

- Total Open Requests
- Pending Approvals
- Overdue Requests
- Priority Concerns
- Upcoming Renewals
- Active Assets
- Assets Under Repair
- Fleet Maintenance Due
- Expiring Government Documents
- Contract Renewals
- Travel Requests
- Administrative Task Completion

## Assistant Dashboard

- Assigned Requests
- Assigned Tasks
- Overdue Follow-ups
- Pending Documents
- Upcoming Renewals
- Requests Awaiting Coordination

## Employee Dashboard

- My Requests
- Pending Approvals
- Requests In Progress
- Completed Requests
- Latest Updates
- Notifications

All metrics must use real, authorized system data.

Never display fabricated totals as live business metrics.

---

# 26. SECURITY AND AUDITING

Security requirements apply to every module.

## Access Controls

- User type
- Company
- Department
- Record ownership
- Assigned employee
- Workflow stage
- Approval authority
- Document sensitivity
- Export permissions

## Sensitive Information

Protect:

- Passport records
- Visa documents
- Personal identification
- Bank documentation
- Corporate card information
- Employee-sensitive attachments

## Audit Events

Record:

- Record creation
- Record modification
- Record deletion where authorized
- Status changes
- Approval decisions
- Assignment changes
- File uploads
- Sensitive document access
- Import operations
- Export operations
- Document generation
- Signature events

Never allow ordinary users to alter historical audit events.

---

# 27. DEVELOPMENT ROADMAP

## Phase 2.1 — Employee Requests

Implement:

- Raise a Concern
- Request Supplies
- My Requests
- Attachments
- Employee request tracking
- Submission lifecycle
- Employee notifications

## Phase 2.2 — Approvals and Administration

Implement:

- Approval inbox
- Approval configuration
- Approval timelines
- Task assignment
- Priority management
- SLA monitoring
- Escalations
- Notifications

## Phase 2.3 — Assets

Implement:

- Asset registry
- Asset assignment
- Asset transfers
- Repairs
- Receiving
- Issuance documents

## Phase 2.3a — Equipment Inventory

Added after Phase 2.3 shipped. Implement:

- Inventory items and storage locations
- Stock in, issue, transfer, return, adjustment and write-off movements
- Link to Receiving Proof (stock in) and Request Supplies (reserve and issue)
- Low-stock alerts and reorder suggestions
- Physical counts with variance and approved adjustments
- Stock cards and movement history

## Phase 2.4 — Fleet

Implement:

- Vehicle registry
- Vehicle maintenance
- Registration monitoring
- Insurance monitoring
- Fleet cards
- RFID
- Finance coordination

## Phase 2.5 — Compliance

Implement:

- Government registrations
- Compliance documents
- Renewal calendar
- BOC case tracking
- Expiry notifications

## Phase 2.6 — Travel and Immigration

Implement:

- Flight bookings
- Hotel bookings
- Employee visas
- Expat visas
- Passport renewals
- Travel requirements

## Phase 2.7 — Contracts and Banking

Implement:

- Lease contracts
- Staff house contracts
- Contract renewals
- Corporate cards
- Bank applications
- Finance coordination

## Phase 2.8 — Import and Export

Implement reusable:

- Excel templates
- CSV templates
- Automatic field mapping
- Manual mapping
- Validation
- Bulk import
- Export processing
- Error reports
- Import/export audit logs

Integrate the shared engine progressively into completed operational modules rather than waiting to retrofit every module at the end.

## Phase 2.9 — Documents and Reports

Implement:

- PDF document generation
- Printable forms
- Signature-ready documents
- Document control numbers
- Document versioning
- Report generation
- Dashboard analytics
- Excel and PDF report exports

---

# 28. DEFINITION OF DONE

A module is complete only when:

1. The page is accessible.
2. The UI is functional.
3. Records persist in the database.
4. Required fields are validated.
5. CRUD operations work where applicable.
6. Domain-specific actions work.
7. Permissions are enforced server-side.
8. Company and department scopes are respected.
9. Approval workflows work where required.
10. Attachments work where applicable.
11. Search, filters, sorting, and pagination work.
12. Status changes are auditable.
13. Notifications work where required.
14. Excel templates are available where applicable.
15. Excel/CSV import works where permitted.
16. Field mapping is functional.
17. Import validation and error reporting work.
18. Excel/CSV export works where applicable.
19. PDF reports are generated where applicable.
20. Official documents can be generated where required.
21. Signature-ready layouts work for relevant forms.
22. Sensitive information is protected.
23. Error and empty states work.
24. Relevant automated tests pass.
25. Existing functionality remains intact.
26. Completion is verified and documented.

For sensitive or read-only modules, explicitly document and test exceptions to import, export, and document generation requirements.

---

# 29. TESTING REQUIREMENTS

Implement tests covering:

- Successful record creation
- Invalid submissions
- Unauthorized access
- Cross-company access denial
- Employee access restrictions
- Approval authorization
- Invalid approval transitions
- Duplicate submissions
- Failed uploads
- File validation
- Excel imports
- Incorrect field mapping
- Invalid dates
- Duplicate records
- Partial import failures
- Import retries
- Export permissions
- CSV formula injection
- PDF layout and page breaks
- Document versioning
- Signature integrity
- Large record sets
- Finance handoff errors
- Renewal notifications

Run the project's existing validation, lint, typecheck, build, and test commands.

Report actual results, not assumed results.

---

# 30. FINAL EXECUTION INSTRUCTIONS

Act as the Principal Full-Stack Engineer responsible for completing the Getmeds Executive Admin application.

## Instructions

1. Inspect the complete existing application.
2. Read all project documentation.
3. Identify existing functionality.
4. Identify Coming Soon modules.
5. Identify current backend and database configuration.
6. Create a dependency-aware implementation plan.
7. Begin implementing real functionality.
8. Start with Employee Requests and Concerns.
9. Continue with approvals and administrative work queues.
10. Implement each operational module in the defined sequence.
11. Integrate reusable Excel import/export capabilities.
12. Implement canonical field mapping and validation.
13. Generate official printable and signature-ready PDF documents.
14. Implement reports using real database records.
15. Test each completed module.
16. Preserve existing navigation and UI architecture.
17. Update documentation as functionality is completed.
18. Avoid unnecessary dependencies and rewrites.
19. Never mark unimplemented functionality as completed.
20. Continue through remaining modules as execution capacity allows, explicitly documenting unfinished work.

## UI Governance

Preserve the existing approved design baseline.

Linus remains the designated Frontend/UI/UX authority for changes beyond the approved visual design.

Functional development must not introduce unauthorized visual redesigns.

## Expected Result

A fully functional, database-backed, permission-controlled Corporate Services Management System supporting:

- Admin
- Assistant
- Employee
- Cross-department requests
- Operational approvals
- Corporate assets
- Fleet management
- Government compliance
- Travel and immigration
- Contracts
- Corporate banking coordination
- Excel/CSV import and export
- Automatic field mapping
- Printable reports
- Professional PDF documents
- Signature-ready forms
- Notifications
- Audit trails
- Enterprise reporting

**Final Rule: Every implemented module must perform real business operations. A finished-looking interface without working backend functionality is not considered complete.**
