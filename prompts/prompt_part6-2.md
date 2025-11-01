Continue the PartsDB dark UI implementation by completing the **ImportCsv.tsx** page.

## Goals
Make the CSV import fully functional and match the dark theme styling of the Components page.

---

## Functional requirements
1. Use the `/api/import/csv` endpoint.
2. Must send `multipart/form-data` with:
   - field: `file` (CSV)
   - field: `dry_run` (boolean)
3. Show upload progress (spinner or subtle loader).
4. On success:
   - Display summary: Created / Updated / Skipped / Errors.
   - If “errors” exist, render a collapsible errors table (row, reason).
5. On failure:
   - Show error toast with clear message.
6. Disable upload button during processing.

---

## UI / Styling requirements
* Use a **Card** layout.
* Top: title “Import Components from CSV”.
* Inside:
  - File picker using shadcn `<Input type="file" />`.
  - Dry-run toggle (checkbox).
  - Upload button (`<Button>` small, accent color).
* Below form:
  - Result summary card, showing counters with colored badges.
  - If error rows exist → render compact table using `<Table>`.

Example summary section layout:
```

<Summary>
  <Badge color="green">Created: 45</Badge>
  <Badge color="yellow">Updated: 19</Badge>
  <Badge color="gray">Skipped: 3</Badge>
  <Badge color="red">Errors: 2</Badge>
</Summary>
```

* Background: var(--bg)
* Cards: var(--surface)
* Text: var(--text)
* Borders: var(--border)
* Accent: var(--accent)
* Compact vertical rhythm (no excessive whitespace)

---

## Implementation details

* Use `useState` for file, dryRun, loading, and result.
* Use `axios.post("/api/import/csv", formData, { headers, onUploadProgress })`.
* Wrap UI in try/catch to handle 400/500 errors gracefully.
* After success, reset `file` input but keep the summary visible.
* Allow re-import (button enabled again after completion).

---

## Bonus (optional but ideal)

* Add a small info box:

  > “The CSV must include headers like MPN, Manufacturer, Value, Package, Description, Datasheet URL, etc.”
* Add support for drag-and-drop (bonus points).
* Animate summary appearing with fade-in.

---

## Constraints

* Use only shadcn/ui and Tailwind.
* No third-party file upload libs.
* Keep consistent with the dark theme variables defined in index.css.
* Must be responsive on narrow viewports.

---

## Expected result

* User selects a CSV → clicks Upload.
* API is called successfully.
* Summary and errors (if any) are displayed nicely.
* Works reliably with large CSVs (~1–2 MB).
* Matches the look and feel of the Components page and Django admin dark theme.