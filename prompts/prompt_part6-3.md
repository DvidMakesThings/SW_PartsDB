Implement a new dark-themed `ComponentDetail.tsx` page for PartsDB.

---

## Purpose
Display detailed information about a single component with tabs:
**Overview**, **Inventory**, **Attachments**.
Match the dark compact theme from Components and ImportCsv pages.

---

## 1. Routing
Path: `/components/:id`
Fetch component data from `/api/components/{id}/`.

Tabs:
- Overview (default)
- Inventory → `/api/inventory/?component={id}`
- Attachments → `/api/attachments/?component={id}`

---

## 2. Layout
Use shadcn/ui components:
`<Tabs>`, `<Card>`, `<Table>`, `<Button>`, `<Badge>`.

Base layout:
```

<main className="p-6 bg-[var(--bg)] text-[var(--text)] min-h-screen">
  <h1 className="text-lg font-bold mb-4">{component.mpn}</h1>
  <Tabs defaultValue="overview">
    <TabsList>
      <TabsTrigger value="overview">Overview</TabsTrigger>
      <TabsTrigger value="inventory">Inventory</TabsTrigger>
      <TabsTrigger value="attachments">Attachments</TabsTrigger>
    </TabsList>

```
<TabsContent value="overview">...</TabsContent>
<TabsContent value="inventory">...</TabsContent>
<TabsContent value="attachments">...</TabsContent>
```

  </Tabs>
</main>
```

---

## 3. Overview Tab

* Card layout showing:

  * MPN
  * Manufacturer
  * Value
  * Package
  * Description
  * Category (L1 / L2)
* Add button **“Fetch Datasheet”** → `POST /api/components/{id}/fetch_datasheet/`

  * Shows spinner and toast message on success/failure
* If datasheet URL exists → show link and download button.

---

## 4. Inventory Tab

* Fetch `/api/inventory/?component={id}`.
* Table columns:

  * Location
  * Quantity
  * Reserved
  * Available
  * Supplier
  * Last Updated
* Quantity should be editable inline (PATCH request).
* Add button “Add Item” opens modal to create new inventory record.

---

## 5. Attachments Tab

* Fetch `/api/attachments/?component={id}`.
* Display list with:

  * Filename
  * Type (datasheet, 3D, photo)
  * File size
  * SHA-256 hash (truncated)
  * Download link
* Add small badge per type for color coding.

---

## 6. Styling

Follow same dark variables:

```
--bg: #121212;
--surface: #1e1e1e;
--text: #e0e3ea;
--accent: #0ea5e9;
--border: #2a2d35;
```

Cards and tables must be compact, subtle borders, hover highlight using `bg-[var(--surface)]/70`.

Tabs and buttons use accent blue highlights.
Everything fully responsive.

---

## 7. Behavior

* Use `useEffect` + axios for data fetching.
* Show loading spinner on each tab separately.
* Gracefully handle 404 / missing component.
* Reuse FadeIn component for smooth transitions.
* Reuse Toasts for notifications.

---

## 8. Bonus (optional but ideal)

* Add top-right “Edit in Admin” link → opens Django admin `/admin/inventory/component/{id}/change/`.
* Add breadcrumb: “← Back to Components”.
* Add summary chip (stock count total) in Overview header.

---

## 9. Constraints

* No extra frameworks beyond shadcn/ui and Tailwind.
* Keep it visually consistent with ImportCsv and Components.
* Maintain small typography and tight layout.

---

## Expected result

A modern, dark-themed detail view with tabs, data fetching, and interaction support.
Looks and feels like a professional internal admin panel.