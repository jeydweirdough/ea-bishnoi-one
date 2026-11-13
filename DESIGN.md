---
name: Executive Admin
description: Bishnoi One corporate services, set as a near-monochrome operating sheet where the only color means "you are here" or "this is live".
colors:
  accent: "#a6c23f"
  ink: "#111111"
  ink-2: "#474747"
  ink-3: "#6b6b6b"
  mute: "#a6a6a6"
  edge: "#cfcfcf"
  line: "#e6e6e6"
  hover: "#ebebea"
  rail: "#f2f2f2"
  canvas: "#fafafa"
  sheet: "#ffffff"
typography:
  display:
    fontFamily: "Poppins, ui-sans-serif, system-ui, sans-serif"
    fontSize: "44px"
    fontWeight: 600
    lineHeight: 1.1
    letterSpacing: "-0.028em"
  headline:
    fontFamily: "Poppins, ui-sans-serif, system-ui, sans-serif"
    fontSize: "32px"
    fontWeight: 600
    lineHeight: 1.1
    letterSpacing: "-0.022em"
  title:
    fontFamily: "Poppins, ui-sans-serif, system-ui, sans-serif"
    fontSize: "15px"
    fontWeight: 600
    lineHeight: 1.35
    letterSpacing: "-0.005em"
  lead:
    fontFamily: "Poppins, ui-sans-serif, system-ui, sans-serif"
    fontSize: "17px"
    fontWeight: 500
    lineHeight: 1.55
  body:
    fontFamily: "Poppins, ui-sans-serif, system-ui, sans-serif"
    fontSize: "14px"
    fontWeight: 500
    lineHeight: 1.45
  label:
    fontFamily: "Poppins, ui-sans-serif, system-ui, sans-serif"
    fontSize: "12px"
    fontWeight: 500
    lineHeight: 1.3
    fontFeature: "\"tnum\" 1"
rounded:
  chip: "5px"
  tag: "6px"
  ctl: "8px"
  panel: "10px"
  palette: "14px"
  sheet-top: "16px"
  pill: "9999px"
spacing:
  row-gap: "2px"
  inset-x: "20px"
  inset-x-mobile: "16px"
  stack: "20px"
  section: "40px"
  topbar: "56px"
  tabbar: "64px"
  sidebar: "276px"
  rail: "64px"
components:
  button-primary:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.sheet}"
    typography: "{typography.body}"
    rounded: "{rounded.ctl}"
    padding: "0 14px 0 12px"
    height: "40px"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.ink-2}"
    rounded: "{rounded.ctl}"
    size: "36px"
  button-ghost-hover:
    backgroundColor: "{colors.hover}"
    textColor: "{colors.ink}"
  search-trigger:
    backgroundColor: "{colors.sheet}"
    textColor: "{colors.ink-3}"
    rounded: "{rounded.ctl}"
    padding: "0 12px"
    height: "36px"
  status-chip:
    backgroundColor: "{colors.sheet}"
    textColor: "{colors.ink}"
    rounded: "{rounded.pill}"
    padding: "0 14px 0 10px"
    height: "32px"
  code-tag:
    backgroundColor: "{colors.sheet}"
    textColor: "{colors.ink-3}"
    typography: "{typography.label}"
    rounded: "{rounded.tag}"
    padding: "2px 6px"
  option-chip:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink-2}"
    typography: "{typography.label}"
    rounded: "{rounded.chip}"
    padding: "1px 6px"
  sheet:
    backgroundColor: "{colors.sheet}"
    rounded: "{rounded.panel}"
    padding: "12px 20px"
  nav-row:
    backgroundColor: "transparent"
    textColor: "{colors.ink-2}"
    rounded: "{rounded.ctl}"
    height: "36px"
  nav-row-current:
    backgroundColor: "{colors.sheet}"
    textColor: "{colors.ink}"
  tab-bar:
    backgroundColor: "{colors.rail}"
    textColor: "{colors.ink-3}"
    height: "{spacing.tabbar}"
---

# Design System: Executive Admin

## Overview

**Creative North Star: "The Monochrome Operating Sheet"**

Executive Admin is a near-monochrome product world. One neutral scale runs from paper white to near-black ink, with a second, slightly cooler layer for the chrome (top bar, sidebar, tab bar). A single chartreuse accent is rationed to the few places that mean "you are here" or "this is live": the current-location dot, the Coming Soon ring, the ring inside the Mark, and the focus halo. Everything else is carried by weight, hairlines and tone.

Density is that of an operating tool. Rows are 36px on desktop and at least 44px wherever a finger lands. Content sits on white sheets with 1px hairlines over a faint canvas, and every module carries a form code (EA-04.4) that breadcrumbs, search, indexes and sibling lists all share. Depth is nearly absent. Only floating layers (menus, the command palette, the mobile module sheet) lift off the page.

The world rejects the category default of a colored sidebar, gradient KPI cards and icon-tile grids. Color is information, never decoration.

**Key Characteristics:**
- One neutral scale plus one rationed chartreuse accent; the accent is never text and never a fill behind text.
- Poppins only, in Regular (400), Medium (500) and SemiBold (600, the system's "bold"); hierarchy comes from weight and size, not color.
- Hairline construction: 1px #e6e6e6 dividers, white sheets, 10px panel corners.
- Form codes shown as tabular meta beside every module name.
- Motion: 150–220ms exponential ease-out on state changes only.

## Colors

A neutral ink-on-paper scale with a single acid-chartreuse signal.

### Primary
- **Signal Chartreuse** (accent): the only chromatic color. Used as a 6px solid dot marking the current nav item, tab or sibling, as a 2.5px ring (Coming Soon chip, Approval Inbox button, the Mark), and as the 45%-alpha halo of the focus ring. It never colors text and never sits behind text.

### Neutral
- **Ink** (ink): primary text, the primary button fill, avatar disc, filled route node, selection background, focus outline.
- **Graphite** (ink-2): secondary text, nav rows at rest, summaries, idle icons.
- **Slate** (ink-3): tertiary text such as codes, meta, breadcrumbs and helper lines. It holds at least 4.5:1 on canvas.
- **Ash** (mute): decorative glyphs only (breadcrumb chevrons, row arrows at rest). Never used for text.
- **Edge Grey** (edge): control borders (search trigger, status chip), route connectors, scrollbar thumb, and the off state of the toggle.
- **Hairline** (line): every divider, sheet border and code-tag border.
- **Hover Wash** (hover): the hover fill for rows and ghost buttons on the rail.
- **Rail Grey** (rail): the second neutral layer for top bar, sidebar and tab bar (at 80–90% opacity with backdrop blur on sticky bars). It is also the PWA theme color.
- **Canvas** (canvas): content ground, option chips, and the hover/current fill inside sheets.
- **Sheet White** (sheet): raised sheets, the current nav row, the palette and menus.

### Named Rules
**The Rationed Signal Rule.** The accent appears only as a dot, a ring or a halo. If it would color a word or sit under a word, use ink instead.

**The One Signal Per Location Rule.** Each "you are here" gets exactly one accent dot: a nav row, a tab, or a sibling row. Do not repeat the dot to decorate.

## Typography

**Display Font:** Poppins (400/500/600, self-hosted at build via next/font/google, with ui-sans-serif, system-ui fallback)
**Body Font:** Poppins
**Label/Mono Font:** Poppins with tabular numerals (`.tabular`) for codes and counts

**Character:** A single geometric grotesk used in two weights. Bold carries titles and current state, Medium carries everything else. The body sets stylistic set ss01.

### Hierarchy
- **Display** (600, 30px mobile / 44px desktop, 1.1, -0.028em): the group index title only.
- **Headline** (600, 26px mobile / 32px desktop, 1.1, -0.022em): the module page title, with the code tag baseline-aligned beside it.
- **Title** (600, 15px, -0.005em): sheet headers and mobile sheet group names (17px for the "All modules" sheet heading).
- **Lead** (500, 16px mobile / 17px desktop, 1.55, max 62ch, ink-2): the one-sentence module purpose.
- **Body** (500, 13.5–14.5px): nav rows, field names, list rows. 14px is the default.
- **Label** (500, 11.5–12.5px, tabular): codes, counts, meta and helper lines in ink-3. Always sentence case.

### Named Rules
**The Weight Is State Rule.** Current location is Bold ink; everything at rest is Medium ink-2. Do not signal state with color in type.

**The Code Beside Name Rule.** A module's form code always travels with its name, as a tabular label in ink-3. It is never a heading of its own.

## Layout

The shell is a 56px sticky top bar over a 276px sidebar (it collapses to a 64px icon rail with a width transition, and labels cross-fade) and a content column. The content frame is centered at max 1160px with 16/24/40px side padding (mobile/tablet/desktop) and 20px or 32px top padding. Module pages use a two-column grid on desktop (`minmax(0,1fr) 320px`, gap 24px) with the main sheets left and the access and sibling sheets right. Sheets stack with 20px gaps. The header block caps at 760px.

On viewports below 1024px the sidebar is replaced by a 64px bottom tab bar (respecting the safe-area inset) and a 92dvh "All modules" sheet that slides up. Breadcrumbs collapse to a single back-link to the parent on phones. Every tappable element on mobile is at least 44px tall. The palette goes full-height on mobile and becomes a 640px centered dialog at 12vh from md up.

Inside sheets, rows use 16px (mobile) or 20px (desktop) horizontal inset and 12–14px vertical padding. Field lists split into two columns from sm up, divided by a hairline.

## Elevation & Depth

The page is flat. Depth comes from tonal layering (rail grey chrome, canvas ground, white sheets) and 1px hairlines. The current nav row is lifted by a 1px hairline ring (`0 0 0 1px` line), not a shadow. A single soft shadow exists, and only floating layers use it.

### Shadow Vocabulary
- **Float** (`box-shadow: 0 12px 32px -8px rgb(17 17 17 / 0.18), 0 2px 6px rgb(17 17 17 / 0.06)`): the account menu, the command palette dialog (md+) and the mobile module sheet. Nothing resting on the page gets it.

### Named Rules
**The Float Only Rule.** If it does not overlay other content, it has no shadow. Sheets are separated by hairlines and tone.

## Shapes

Corners are soft and tiered by size: 5px for option chips, kbd hints and skeleton icons; 6px for code tags, sub-nav rows and small text buttons; 8px for every control (buttons, nav rows, search trigger, icon buttons); 10px for panels and sheets. Overlays go larger (14px for the palette dialog, 16px for the top of the mobile sheet). Status chips, avatars, toggles and dots are full circles or pills. Borders are always 1px. Route nodes are 14px circles with 2px borders joined by 1px connectors. The empty "Fields to be defined" state uses a dashed edge-grey border instead of a sheet.

## Components

### Buttons
Quiet and confident: ink or nothing.
- **Shape:** gently rounded (8px).
- **Primary:** an ink fill with a white Medium 14px label, 40px tall, led by a 12px accent ring. Hover drops opacity to 90%.
- **Ghost / Icon:** transparent with an ink-2 icon (18px lucide, 1.75 stroke), 36px on desktop and 44px on mobile. Hover takes the hover-wash fill and ink.
- **Focus:** a 2px ink outline at 2px offset plus a 6px chartreuse halo at 45% alpha, on a 6px radius.

### Chips
- **Status chip:** a 32px pill with a white fill, an edge-grey border and a Bold 13.5px label, led by a 12px accent ring. It reads "Coming soon" across Phase 1.
- **Code tag:** tabular 12px ink-3 on white inside a hairline, 6px radius.
- **Option chip:** 12px ink-2 on canvas inside a hairline, 5px radius. It lists a field's allowed values.

### Cards / Containers
- **Corner Style:** 10px.
- **Background:** sheet white on canvas.
- **Shadow Strategy:** none (see Elevation).
- **Border:** a 1px hairline, with a hairline under the header.
- **Internal Padding:** 12px by 16/20px for the header; rows use the same inset. The header pairs a Bold 15px title with tabular ink-3 meta on the right.

### Inputs / Fields
- **Search trigger:** 36px tall and up to 420px wide, a white fill, an edge-grey border, a 14px ink-3 placeholder and a kbd hint (5px radius, canvas). On hover the border shifts to mute and the text to ink-2.
- **Palette input:** a borderless 56px row at 16px Medium, with an ink caret. The hairline beneath it is the only frame.

### Navigation
- **Sidebar:** 36px rows on rail grey. At rest they are Medium ink-2, and hover takes the hover wash. Groups are disclosure sections: the label links to the group page and a separate chevron button rotates 90° to open. Child items hang from a 1px hairline spine. The current item is Bold ink on a white row with a hairline ring and a trailing accent dot. In the collapsed rail the dot sits at the icon's top right.
- **Top bar:** rail grey at 80–90% with backdrop blur. It holds the Mark and two-line wordmark (Bold 15px name, 11.5px ink-3 family line), the centered search trigger, notifications and the account/role menu.
- **Tab bar (mobile):** five tabs with 22px icons and 11.5px labels. The active tab is Bold ink with a 2px icon stroke and an accent dot on the icon.
- **Breadcrumbs:** 13px ink-3 with mute chevrons. Links are Medium ink-2 and the current page is Medium ink.

### Command Palette (signature)
This dialog indexes every module by name and code. Results are rows of a tabular code column (64px), a name and a group line. The cursor row takes a canvas fill and a hairline ring and shows an enter glyph. Rows reveal with `rise-in` (200ms, 6px rise and 2px blur clearing), staggered 18ms per row and capped at 10. The footer carries the keyboard legend and a tabular result count.

### Approval Route
A horizontal (sm+) or vertical (mobile) chain of 14px nodes. The first node is filled ink, intermediate nodes are edge-grey outlines and the final node is an ink outline, joined by 1px edge-grey connectors. Step labels are 13.5px Medium.

## Do's and Don'ts

### Do:
- **Do** keep the accent to dots (6px), rings (2.5px border) and the focus halo; mark exactly one "you are here" per navigation context.
- **Do** separate surfaces with 1px hairlines (line) and tone (rail, canvas, sheet) rather than shadows.
- **Do** pair every module name with its tabular form code in ink-3.
- **Do** use Poppins SemiBold for titles and current state and Poppins Medium for everything else.
- **Do** keep touch targets at 44px or more on mobile and 36px rows on desktop.
- **Do** animate state changes only, 150–220ms on the expo ease-out (`cubic-bezier(0.16, 1, 0.3, 1)`), and collapse to near-instant under reduced motion.

### Don't:
- **Don't** set text in the accent or place text on an accent fill.
- **Don't** give a resting sheet or card a shadow; the float shadow belongs to overlays only.
- **Don't** introduce a colored sidebar, gradient KPI cards or icon-tile grids.
- **Don't** use mute (#a6a6a6) for text; it is for decorative glyphs only.
- **Don't** add a second typeface or uppercase tracked labels; labels stay sentence case.


## Iconography & density

- Every group and module has one Lucide icon, chosen for the object the module is about. The icon is resolved by route (`iconForHref` in `web/src/components/icons.tsx`) and reused in the sidebar, search, mobile menu, lists and page headers. Icons are drawn at 1.6 stroke, in ink-3 at rest and ink when active.
- Lists and headers lead with an icon tile (`IconTile`), not a form code. Codes stay quiet: they show as a muted suffix on the status line and in search results only.
- Keep views uncluttered. Long field lists show 6 items and expand on demand. Notes sit inline under the summary instead of in boxes. On phones, links already available in the bottom tab bar are not repeated in the page.

## Working screens (Phase 2.1 – 2.2)

- **One semantic hue.** `--color-danger` (#b42318) marks overdue, rejected and destructive actions, in text and icons only, never as a large fill. Everything else stays on the neutral scale. The accent ring marks "needs you" states (returned, fulfilled-awaiting-confirmation, pending approval stage) and unread notifications.
- **Status is a badge with an icon**, never colour alone. Priority is quiet text; only High and Critical get a flag (Critical's flag is filled).
- **Each request page answers "what happens next" first.** The bordered panel under the title says who holds the request, and holds the only action buttons that apply now. Details, approval route, activity and summary sit below.
- **The approval route reads like a receipt.** Requester → each stage (approved = filled ink, deciding now = accent ring, rejected = danger) → Executive Admin processing.
- **Forms:** long forms are split into titled panels. Optional item details sit behind a "Category, brand and model" disclosure. On phones the Save/Submit bar sticks above the tab bar. Errors appear under the field that caused them, with a summary above the buttons.
- **Dialogs** become bottom sheets on phones and centred dialogs on desktop. A reason field is required for return, reject, cancel, fulfil and reopen.
- **Toasts:** only the most recent one shows, above the tab bar on phones.

## Navigation and density (distill pass, 12 Nov 2026)

- **Navigate by task, not by catalogue.**
  - Staff see Home, Requests, In approval, Tasks, My approvals (approvers) and My own requests.
  - Employees see Home, My requests, My approvals (approvers) and Notifications.
  - The model lives in `web/src/lib/menu.ts`.
- **One way to start.** "New request" is the top of the sidebar on desktop and the centred "+" on phones. It opens one question, "What do you need?" (`/me/new`): Report a problem, or Request items.
- **Setup is behind one door.** Admins get a single "Settings" fold. Inside it, Approval routes, Deadlines (SLA), People & access and Audit log share a tab bar, not four sidebar entries.
- **Unbuilt modules live under one "Coming soon" fold.** When a module goes live, add it to `primaryMenu` and `LIVE_MODULES`; don't add a new sidebar group.
- **Phone tabs:**
  - At most five, with "+" always in the centre.
  - Staff: Home, Requests, +, Tasks, More.
  - Employees: Home, +, Requests. Employees with approval duties add Approvals and Alerts. The bell in the top bar covers alerts otherwise.
- **Forms ask the essentials first.**
  - A concern needs only: kind of problem (icon tiles), a few words, details and where.
  - An item request needs only: items, what it's for and when.
  - Priority, dates, asset, delivery, notes and a custom title wait under "More options". Item requests title themselves from the items.
- **Counts are a strip, not a wall of cards.** `CountStrip` shows numbers that link to their lists.
- **Lists show search and status; the rest waits.** Type, owner and deadline filters and sorting sit behind one "Filters" button that shows how many are active.
- **Request page:** "At a glance" shows only what decides the next step (who, priority, owner, deadline). The rest is under "More details". Activity shows the latest five events, and the comment box opens on demand.
- **Words:** plain verbs and nouns ("Send request", "Report a problem", "Being worked on", "Urgent"). Codes and catalogue names stay in search and breadcrumbs.

## Wording and UX laws (12 Nov 2026)

Copy is corporate and conventional. People find their way by what they already know from other company systems.

**Five UX laws every screen follows**

1. **Jakob's Law (familiarity).** Use the labels and patterns of standard corporate and ERP systems:
   - "Information", not "At a glance".
   - "Purchase request", "Physical count", "Record payment", "Import mode".
   - Empty states read "No [records] …", for example "No matching records" or "No assets under repair". Never "Nothing …".
2. **Hick's Law (fewer choices).**
   - One primary action per screen.
   - Secondary actions are ghost buttons.
   - Rarely used fields sit under "More options".
3. **Fitts's Law (reachable targets).**
   - Primary actions are full-height buttons placed at the top of the record.
   - On phones, buttons are at least 40px tall and the main action is in the bottom bar.
4. **Miller's Law (chunking).**
   - Count strips hold four figures.
   - Lists are grouped into small panels.
   - Long forms are split into essentials and "More options".
5. **Law of Proximity (grouping).**
   - A record's facts sit together in its "Information" panel.
   - Its actions sit together in one row.
   - Its files and documents sit together in the side column.

**Action labels state what is recorded**
- Use "Record bank approval", "Record Finance confirmation" and "Mark as submitted to bank".
- Don't use bare outcomes such as "Bank approved" or "Finance paid". A button records an event; it does not claim one.

**Upload first, type last**
- Forms for documents (registrations, passports and visas, contracts, vehicles and their renewals, fleet and corporate cards) open with an **Upload the document** panel above the fields.
- Reading fills the fields. Each filled field shows "Read from document", or a bordered **Verify** tag when confidence is below 80%.
- The panel reports how many details were read and how many need checking.
- Typing in a field clears its tag. The uploaded file is attached to the record on save.

**Adding a person in place**
- Person dropdowns for the subject of a record end with **+ Add a person not in the list…**. It opens an inline panel under the field; never a second dialog.
- Fields: first, middle and last name, suffix, gender, date of birth with the age worked out, or the age alone.
- The chosen person's gender and age show under the field in muted text.

**Item photos**
- Physical items (assets, stock, vehicles) show their main photo wherever they are listed: a 48px rounded thumbnail in place of the icon tile, falling back to the icon.
- Record pages have a **Photos** panel: a 4:3 main photo, a thumbnail strip, and **Take photo** (camera) plus **Upload**.
- New-item forms carry the same buttons with previews; the first photo is marked **Main**.

**Page header actions**
- One labelled primary button (e.g. *Register asset*). Every secondary action (Import, Export, page settings such as the default card limit) goes in the **⋯ More actions** menu (`MoreMenu`, via `DataTools extra`).
- Desktop (≥1024px): the actions sit top-right, level with the title. Phones and tablets: they sit under the summary, aligned with the title text.

**Module sub-navigation**
- **One home per record.** A sub-menu entry must show something no record page already shows. Data about one record (a vehicle's renewals, fuel card, RFID or service log; an asset's repairs) lives on that record's page. Fleet-wide views of it are **filter chips on the main list** (e.g. *Due soon*), never another menu entry. Keep each sub-menu to 2–4 screens (Hick's law).
- Modules with several screens (Assets, Fleet, Compliance, Travel, Contracts, Banking) show those screens in a **vertical sub-menu** on desktop (≥1024px). It sits to the left of the content, under the module name, and sticks while scrolling. Long labels wrap; they are never cut off.
- On phones and tablets, the same screens are a swipeable tab strip, scrolled so the current tab is in view.
- No visible horizontal scrollbars anywhere. Strips that can swipe use `no-scrollbar`.
- Short tab sets that always fit (Settings, Reports) stay horizontal.
