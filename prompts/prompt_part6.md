## ⚙️ Copilot Prompt — Redesign PartsDB Frontend (Modern UI, Dark, Functional)

````
You are improving the PartsDB frontend UI. The current frontend is visually outdated, oversized, and lacks usability.
You must completely refactor it using **React + Vite + TypeScript + TailwindCSS** with a **dark, professional theme** similar to the Django admin style.

---

## 1. Design goals
* Use a dark theme: near-black background, neutral-gray cards, cyan/blue highlights.
* Minimal spacing, compact tables, small text (12–14px).
* Consistent top navigation bar with logo “PartsDB” + links to Components / Inventory / Import.
* No giant icons. Use small Lucide icons or Heroicons at 16px max.
* Fully responsive — tables and filters adapt without horizontal scroll.
* Keep everything in `frontend/src/`, maintain the file structure.

---

## 2. Functional fixes
* CSV upload (ImportCsv.tsx) must work end-to-end.
  - Use multipart/form-data upload to `/api/import/csv`.
  - Show progress and server response summary (created, updated, errors).
  - Display the errors table if available.
  - Disable button while uploading.
* Component list and filters must query `/api/components/` using query params (`manufacturer`, `category_l1`, `package_name`, `in_stock_only`, `search`).
* Pagination works (Next/Prev buttons enabled properly).
* Component detail page shows tabs: Overview | Inventory | Attachments.
  - Overview shows MPN, Manufacturer, Value, Package, Description.
  - Inventory shows stock table with editable quantities.
  - Attachments shows list of attached files and download links.

---

## 3. Style and layout
Use TailwindCSS and shadcn/ui components (Card, Button, Input, Table, Tabs).
Theme variables:
```css
:root {
  --bg: #0f1117;
  --surface: #1b1e25;
  --text: #e0e3ea;
  --accent: #3b82f6;
  --border: #2a2d35;
}
````

All pages must follow this style. Use `<main className="p-6 text-sm bg-[var(--bg)] text-[var(--text)] min-h-screen">`.

---

## 4. Pages to rebuild

### 4.1 App.tsx

* Implement a responsive navbar with logo and route links.
* Routes:

  * `/components` → Components.tsx
  * `/inventory` → Inventory.tsx
  * `/import` → ImportCsv.tsx
* Use `react-router-dom@6` and Tailwind grid layout.

### 4.2 Components.tsx

* Show filters horizontally in compact “filter bar”:

  * Search input
  * Manufacturer dropdown (multi-select)
  * Category dropdown
  * Package dropdown
  * “In stock only” checkbox
* Results in a dense table with columns:
  MPN | Manufacturer | Value | Package | Category | In Stock | Actions
* Each row has a small “View” link (or eye icon) → ComponentDetail.tsx.
* Use `useEffect` to fetch `/api/components/` with current filters and pagination.
* Add loading spinner (tiny inline) and error message area.

### 4.3 ComponentDetail.tsx

* Tabs: Overview / Inventory / Attachments.
* Each tab in a Card.
* Use `GET /api/components/{id}/` and `GET /api/inventory?component=id`.
* “Fetch Datasheet” button triggers POST `/api/components/{id}/fetch_datasheet/` and shows toast.

### 4.4 Inventory.tsx

* Table view of `/api/inventory/`.
* Editable quantity field (PATCH request).
* Search by location and supplier.

### 4.5 ImportCsv.tsx

* File upload form: choose file, dry-run checkbox.
* Show spinner while uploading.
* After upload, render a summary table:
  Created | Updated | Skipped | Errors (if any).
* If errors exist, render a collapsible table showing rows and messages.

---

## 5. Components to add (frontend/src/components/)

* **Navbar.tsx** – reusable top navigation.
* **Card.tsx** – shadcn/ui style wrapper.
* **Table.tsx** – compact table with subtle hover.
* **Button.tsx** – small rounded button component.
* **Toast.tsx** – show success/error notifications.

---

## 6. Theme consistency

Use Tailwind + shadcn/ui dark variant:

```bash
npx shadcn-ui init
npx shadcn-ui add button input table tabs card select checkbox
```

Color palette:

* Background: slate-900 / zinc-900
* Cards: slate-800
* Borders: slate-700
* Accent: blue-500
* Text: slate-100

---

## 7. Testing expectations

* `npm run dev` starts clean, no missing dependencies.
* `/components` loads real API data.
* `/import` successfully uploads CSV and shows results.
* Dark theme looks consistent with Django admin (same color tone and layout compactness).
* No oversized icons or huge buttons.

---

## 8. README update

Add section **Frontend UI Revamp**:

> The React frontend has been redesigned for a dark, compact layout consistent with Django admin.
> Components list, Inventory, and CSV Import now have responsive, minimal layouts with working API integration.

---

## 9. Constraints

* Keep all existing routes and API endpoints intact.
* No CSS frameworks other than Tailwind + shadcn/ui.
* Do not add Material UI or Bootstrap.
* The UI must be functional, aesthetic, and responsive.

---

Implement step-by-step:

1. Replace layout and CSS with dark theme.
2. Fix CSV upload and response display.
3. Add filters and pagination.
4. Polish all tables and typography.
5. Verify mobile responsiveness.

```
