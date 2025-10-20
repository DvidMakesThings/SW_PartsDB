#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DMT CSV Builder GUI (refactored with graph-section filtering and dbdata storage)

Short summary:
- Downloads each datasheet into: dbdata/<name_of_datasheet>/<name_of_datasheet>.pdf
- OCR-extracts pages; saves debug images/TSV under dbdata/<name>/debug/ when enabled
- Detects and removes 'Typical Characteristics' graph sections and graph-heavy pages
- Only the filtered pages are serialized and sent to the LLM
- Writes a mapping report in dbdata/<name>/debug_pdf_mapping.txt
- Deletes the downloaded PDF after prefill to keep the workspace clean
"""

import os, sys, re, csv, json, html, tempfile, pathlib
from collections import defaultdict, OrderedDict
from datetime import datetime as _dt

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog

# ---------------------------------------------------------------------
# App-level constants and helpers
# ---------------------------------------------------------------------

APP_NAME = "DMT CSV Builder"
SCHEMA_FILENAME = "dmt_schema.json"
CONFIG_FILENAME = "dmt_config.json"
ID_FIELDS = ["TT", "FF", "CC", "SS", "XXX", "DMTUID"]


def here_path(*parts):
    base = os.path.dirname(os.path.abspath(sys.argv[0]))
    return os.path.join(base, *parts)


def read_json_safe(path, fallback=None):
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        if fallback is not None:
            return fallback
        raise


def write_json_safe(path, obj):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)


def read_csv_rows(path):
    if not os.path.exists(path):
        return []
    for enc in ("utf-8-sig", "utf-8", "latin1"):
        try:
            with open(path, "r", encoding=enc, newline="") as f:
                reader = csv.DictReader(f)
                return list(reader)
        except Exception:
            continue
    try:
        with open(path, "r", errors="replace") as f:
            reader = csv.DictReader(f)
            return list(reader)
    except Exception:
        return []


def write_csv_rows(path, fieldnames, rows):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow(
                {k: ("" if row.get(k) is None else str(row.get(k))) for k in fieldnames}
            )


def build_dmt_code(tt, ff, cc, ss, xxx):
    return f"DMT-{tt}{ff}{cc}{ss}{xxx}"


# ---------------------------------------------------------------------
# Schema model
# ---------------------------------------------------------------------


class DMTSchema:
    def __init__(self, schema_dict):
        self.schema = schema_dict or {}
        self.domains = OrderedDict()
        self.families = {}
        self.cc_map = {}
        self.ss_map = {}
        self._parse_schema()

    def _parse_schema(self):
        for d in self.schema.get("domains", []):
            tt = d.get("tt")
            name = d.get("name", f"TT {tt}")
            if tt:
                self.domains[tt] = name
                fams = OrderedDict()
                for f in d.get("families", []):
                    ff = f.get("ff")
                    fname = f.get("name", f"FF {ff}")
                    if ff:
                        fams[ff] = fname
                self.families[tt] = fams

        fam_guides = self.schema.get("family_cc_ss_guidelines", {})
        for key, guide in fam_guides.items():
            ttff = None
            if "_" in key and key[:4].isdigit():
                ttff = key[:4]
            if not ttff:
                continue
            tt, ff = ttff[:2], ttff[2:4]
            cc = guide.get("cc", {})
            ss = guide.get("ss", {}) or guide.get("ss_vendor_families", {})

            cc_od = OrderedDict((str(k).zfill(2), str(v)) for k, v in cc.items())
            ss_od = OrderedDict()
            if isinstance(ss, dict):
                for k, v in ss.items():
                    key_fmt = k if len(str(k)) == 2 else str(k).zfill(2)
                    ss_od[key_fmt] = str(v)
            self.cc_map[(tt, ff)] = cc_od
            self.ss_map[(tt, ff)] = ss_od

    def get_families(self, tt):
        return self.families.get(tt, OrderedDict())

    def get_cc(self, tt, ff):
        return self.cc_map.get((tt, ff), OrderedDict())

    def get_ss(self, tt, ff):
        return self.ss_map.get((tt, ff), OrderedDict())


# ---------------------------------------------------------------------
# CSV data model
# ---------------------------------------------------------------------


class DMTModel:
    """
    Holds rows and controls CSV writing order.
    - Uses uppercase ID fields: TT, FF, CC, SS, XXX, DMTUID
    - Lowercase legacy keys are read for index reconstruction only
    """

    def __init__(self, csv_path=None, fieldnames=None):
        self.csv_path = csv_path
        self.rows = []
        self.index = defaultdict(int)  # base -> max XXX

        self.fieldnames_master = list(
            fieldnames
            or [
                "MPN",
                "Quantity",
                "Value",
                "Description",
                "Datasheet",
                "TT",
                "FF",
                "CC",
                "SS",
                "XXX",
                "DMTUID",
            ]
        )
        self.active_order = list(self.fieldnames_master)

        if csv_path:
            self.load(csv_path)

    def load(self, path):
        self.csv_path = path
        self.rows = read_csv_rows(path)
        if self.rows:
            file_fields = list(self.rows[0].keys())
            for f in file_fields:
                if f not in self.fieldnames_master:
                    self.fieldnames_master.append(f)
        self._rebuild_index()

    def set_active_order(self, columns_in_order):
        for c in columns_in_order:
            if c not in self.fieldnames_master:
                self.fieldnames_master.append(c)
        self.active_order = list(columns_in_order)

    def ensure_fields(self, keys):
        for k in keys:
            if k not in self.fieldnames_master:
                self.fieldnames_master.append(k)

    def _rebuild_index(self):
        self.index.clear()
        for r in self.rows:
            base = (
                str(r.get("TT", "") or r.get("tt", "")).zfill(2)
                + str(r.get("FF", "") or r.get("ff", "")).zfill(2)
                + str(r.get("CC", "") or r.get("cc", "")).zfill(2)
                + str(r.get("SS", "") or r.get("ss", "")).zfill(2)
            )
            xxx_raw = r.get("XXX", "") or r.get("xxx", "")
            xxx = str(xxx_raw).zfill(3) if xxx_raw else ""
            if base and xxx.isdigit():
                self.index[base] = max(self.index[base], int(xxx))

            code = r.get("DMTUID", "")
            if code.startswith("DMT-") and len(code) >= 15:
                digits = code[4:]
                base2, xxx2 = digits[:8], digits[8:11]
                if base2.isdigit() and xxx2.isdigit():
                    self.index[base2] = max(self.index[base2], int(xxx2))

    def next_xxx(self, tt, ff, cc, ss):
        base = f"{tt}{ff}{cc}{ss}"
        self.index[base] += 1
        return f"{self.index[base]:03d}"

    def add_item(self, fixed_codes, form_values):
        tt = fixed_codes["tt"]
        ff = fixed_codes["ff"]
        cc = fixed_codes["cc"]
        ss = fixed_codes["ss"]
        xxx = self.next_xxx(tt, ff, cc, ss)
        code = build_dmt_code(tt, ff, cc, ss, xxx)

        needed = set(form_values.keys()) | {
            "MPN",
            "Quantity",
            "Value",
            "Description",
            "Datasheet",
            "TT",
            "FF",
            "CC",
            "SS",
            "XXX",
            "DMTUID",
        }
        self.ensure_fields(list(needed))

        row = {k: "" for k in self.fieldnames_master}
        row.update(form_values)
        row.update({"TT": tt, "FF": ff, "CC": cc, "SS": ss, "XXX": xxx, "DMTUID": code})
        self.rows.append(row)
        return row

    def save(self, path=None, field_order=None):
        path = path or self.csv_path
        if not path:
            raise ValueError("CSV path not set")

        order = list(field_order or self.active_order)
        for f in self.fieldnames_master:
            if f not in order:
                order.append(f)

        write_csv_rows(path, order, self.rows)
        return path


# ---------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------


class DMTGUI(tk.Tk):
    def __init__(self, schema_path, config_path):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("1400x800")
        self.minsize(880, 560)

        self.schema_path = schema_path
        self.config_path = config_path

        self.schema = DMTSchema(
            read_json_safe(
                schema_path, fallback={"domains": [], "family_cc_ss_guidelines": {}}
            )
        )

        self.app_config = read_json_safe(
            config_path,
            fallback={
                "last_csv": "",
                "dbdata_dir": here_path("dbdata"),
                "save_debug_assets": True,
                "skip_graph_pages": True,
            },
        )

        self._load_field_defs()
        self._load_templates()

        self.model = DMTModel(
            self.app_config.get("last_csv") or None, fieldnames=self.csv_fields
        )

        self._build_menu()
        self._build_form()
        self._build_table()
        self._refresh_table()
        self._populate_tt()
        self.status_var.set(f"CSV: {self.model.csv_path or '(none)'}")

    # --------------------- debug / status ---------------------

    def _dbg(self, msg: str):
        ts = _dt.now().strftime("%H:%M:%S")
        line = f"[DMT-PDF {ts}] {msg}"
        print(line)
        try:
            self.status_var.set(msg)
            self.update_idletasks()
        except Exception:
            pass

    # --------------------- templates ---------------------

    def _load_templates(self):
        """
        Load per-family field templates for each TTFF (e.g., '0203' for MOSFETs)
        from dmt_templates.json in the project root.
        """
        self.templates_path = here_path("dmt_templates.json")
        file_templates = {}
        if os.path.exists(self.templates_path):
            try:
                file_templates = read_json_safe(self.templates_path, fallback={})
            except Exception:
                file_templates = {}
        self.templates = file_templates
        self.fallback_fields = [
            "MPN",
            "Quantity",
            "Package",
            "Manufacturer",
            "Datasheet",
            "Description",
        ]

    def _get_active_template_fields(self, tt_code, ff_code):
        ttff = f"{tt_code}{ff_code}"
        return list(self.templates.get(ttff, self.fallback_fields))

    # --------------------- foldering helpers ---------------------

    def _sanitize_ds_name(self, url: str) -> str:
        from urllib.parse import urlparse

        base = os.path.basename(urlparse(url).path) or "datasheet.pdf"
        name = re.sub(r"\.pdf$", "", base, flags=re.IGNORECASE) or "datasheet"
        name = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_")
        return name or "datasheet"

    def _ensure_dirs(self, base_dir: str, name: str, save_debug: bool):
        ds_dir = os.path.join(base_dir, name)
        os.makedirs(ds_dir, exist_ok=True)
        dbg_dir = os.path.join(ds_dir, "debug") if save_debug else None
        if dbg_dir:
            os.makedirs(dbg_dir, exist_ok=True)
        return ds_dir, dbg_dir

    # --------------------- mapping to UI fields ---------------------

    def _map_product_to_template_fields(self, raw_dict: dict) -> dict:
        mapped = {}
        if not raw_dict:
            self._dbg("Mapping: raw dict empty.")
            return mapped

        tmpl_fields = list(self.form_inputs.keys())
        self._dbg(
            f"Mapping {len(raw_dict)} raw attrs → {len(tmpl_fields)} template fields."
        )

        lower_raw = {k.lower(): v for k, v in raw_dict.items()}
        aliases = {
            "drain to source voltage (vdss)": "Drain to Source Voltage (Vdss)",
            "current - continuous drain (id) @ 25°c": "Current - Continuous Drain (Id) @ 25°C",
            "rds on (max) @ id, vgs": "Rds On (Max) @ Id, Vgs",
            "vgs(th) (max) @ id": "Vgs(th) (Max) @ Id",
            "gate charge (qg) (max) @ vgs": "Gate Charge (Qg) (Max) @ Vgs",
            "input capacitance (ciss) (max) @ vds": "Input Capacitance (Ciss) (Max) @ Vds",
            "power dissipation (max)": "Power Dissipation (Max)",
            "package / case": "Package / Case",
            "supplier device package": "Supplier Device Package",
        }

        matched = 0
        for fld in tmpl_fields:
            v = None
            if fld in raw_dict:
                v = raw_dict[fld]
                reason = "exact"
            else:
                lf = fld.lower()
                if lf in lower_raw:
                    v = lower_raw[lf]
                    reason = "ci"
                else:
                    alias_key = aliases.get(lf)
                    if alias_key and alias_key in raw_dict:
                        v = raw_dict[alias_key]
                        reason = "alias"
                    else:
                        reason = None

            if v:
                mapped[fld] = v
                matched += 1
                self._dbg(f"Map OK [{reason}]  {fld}  <-  {v}")
            else:
                self._dbg(f"Map MISS         {fld}")

        self._dbg(f"Mapping finished. Matched {matched}/{len(tmpl_fields)} fields.")
        return mapped

    # --------------------- GUI build ---------------------

    def _build_menu(self):
        menubar = tk.Menu(self)
        m_file = tk.Menu(menubar, tearoff=0)
        m_file.add_command(label="Open/Choose CSV…", command=self.on_open_csv)
        m_file.add_command(label="Save As…", command=self.on_save_as)
        m_file.add_separator()
        m_file.add_command(label="Exit", command=self.destroy)
        menubar.add_cascade(label="File", menu=m_file)
        self.configure(menu=menubar)

    def _build_form(self):
        frm = ttk.LabelFrame(self, text="New / Edit Item")
        frm.pack(side=tk.TOP, fill=tk.X, padx=10, pady=8)

        # TT (Domain)
        ttk.Label(frm, text="TT (Domain):").grid(
            row=0, column=0, sticky="e", padx=6, pady=4
        )
        self.tt_var = tk.StringVar()
        self.tt_cb = ttk.Combobox(
            frm, textvariable=self.tt_var, state="readonly", width=48
        )
        self.tt_cb.grid(row=0, column=1, sticky="we")
        self.tt_cb.bind("<<ComboboxSelected>>", self.on_tt_change)

        # FF (Family)
        ttk.Label(frm, text="FF (Family):").grid(
            row=0, column=2, sticky="e", padx=6, pady=4
        )
        self.ff_var = tk.StringVar()
        self.ff_cb = ttk.Combobox(
            frm, textvariable=self.ff_var, state="readonly", width=52
        )
        self.ff_cb.grid(row=0, column=3, sticky="we")
        self.ff_cb.bind("<<ComboboxSelected>>", self.on_ff_change)

        # CC (Class)
        ttk.Label(frm, text="CC (Class):").grid(
            row=1, column=0, sticky="e", padx=6, pady=4
        )
        self.cc_var = tk.StringVar()
        self.cc_cb = ttk.Combobox(
            frm, textvariable=self.cc_var, state="readonly", width=52
        )
        self.cc_cb.grid(row=1, column=1, sticky="we")

        # SS (Style/Vendor)
        ttk.Label(frm, text="SS (Style/Vendor):").grid(
            row=1, column=2, sticky="e", padx=6, pady=4
        )
        self.ss_var = tk.StringVar()
        self.ss_cb = ttk.Combobox(
            frm, textvariable=self.ss_var, state="readonly", width=52
        )
        self.ss_cb.grid(row=1, column=3, sticky="we")

        # dynamic panel placeholder (fields from template)
        self.dynamic_frame = ttk.LabelFrame(self, text="Item Details")
        self.dynamic_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=(0, 10))
        self.form_inputs = {}  # key -> StringVar

        # buttons row (MERGED: one button does add or update + save)
        btns = ttk.Frame(self)
        btns.pack(side=tk.TOP, fill=tk.X, padx=10, pady=(0, 10))
        ttk.Button(btns, text="Save Item", command=self.on_save_item).pack(
            side=tk.RIGHT, padx=4
        )
        ttk.Button(btns, text="Choose CSV…", command=self.on_open_csv).pack(
            side=tk.LEFT, padx=4
        )
        ttk.Button(
            btns, text="Prefill from PDF (Ollama)…", command=self.on_prefill_from_pdf
        ).pack(side=tk.LEFT, padx=4)

        # status
        self.status_var = tk.StringVar(value="Ready")
        status = ttk.Label(
            self, textvariable=self.status_var, relief=tk.SUNKEN, anchor="w"
        )
        status.pack(side=tk.BOTTOM, fill=tk.X)

        # label->code maps
        self._tt_label_to_code = {}
        self._ff_label_to_code = {}
        self._cc_label_to_code = {}
        self._ss_label_to_code = {}

        # editing state: None means "new item"; else holds row index in self.model.rows
        self._editing_index = None

    def _build_table(self):
        """
        What changed:
        - The horizontal scrollbar now lives INSIDE `self.table_frame` and is destroyed
        together with the table when the template changes. (Previously it was created
        on the root window, so every refresh added a new one.)
        - The method always tears down the old frame before creating a new tree + bars.
        - Column setup remains the same; autosizing is done elsewhere.
        """
        # Destroy any previous table (this also destroys its scrollbars)
        if hasattr(self, "table_frame") and self.table_frame.winfo_exists():
            self.table_frame.destroy()

        # Outer labeled frame
        self.table_frame = ttk.LabelFrame(self, text="Current Items")
        self.table_frame.pack(
            side=tk.TOP, fill=tk.BOTH, expand=True, padx=10, pady=(0, 10)
        )

        cols = list(self.model.active_order)

        # Treeview
        self.tree = ttk.Treeview(
            self.table_frame, columns=cols, show="headings", height=12
        )
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Headings/initial widths (real sizing is done by _auto_size_columns)
        for c in cols:
            self.tree.heading(c, text=c)
            self.tree.column(c, width=120, minwidth=80, anchor="w", stretch=True)

        # Vertical scrollbar (inside table_frame so it is destroyed with the table)
        sb_y = ttk.Scrollbar(
            self.table_frame, orient="vertical", command=self.tree.yview
        )
        sb_y.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.configure(yscrollcommand=sb_y.set)

        # Horizontal scrollbar — IMPORTANT: also inside table_frame and at the BOTTOM
        sb_x = ttk.Scrollbar(
            self.table_frame, orient="horizontal", command=self.tree.xview
        )
        sb_x.pack(side=tk.BOTTOM, fill=tk.X)
        self.tree.configure(xscrollcommand=sb_x.set)

        # Double-click to load row for editing
        self.tree.bind("<Double-1>", self.on_tree_double_click)

    def _render_dynamic_fields(self, field_list):
        """
        Two-column form renderer (same overall look).
        - Normal row: [L-Label][L-Entry]    [R-Label][R-Entry]
        - If a field key contains ' @ ', we:
            * Use ONLY the LEFT part of the key as the outer label (e.g., "Rds On (Max)").
            * Render two inputs inside that single cell: [EntryL]  '@ right_key:' [EntryR].
            (No duplicate left sublabel; right sublabel is shown inline after '@'.)
        This applies to either the left or right side independently.
        - CSV/table columns remain the ORIGINAL combined keys.
        - self.at_join_map maps combined -> (left_key, right_key) for save/load.
        """
        # Clear previous UI
        for w in self.dynamic_frame.winfo_children():
            w.destroy()
        self.form_inputs.clear()
        self.at_join_map = {}

        # Editable columns (exclude ID fields)
        columns = [f for f in field_list if f not in ID_FIELDS]
        self.model.ensure_fields(columns)

        # Grid: 0=L-label, 1=L-cell, 2=spacer, 3=R-label, 4=R-cell
        for c in (1, 4):  # entries expand
            self.dynamic_frame.columnconfigure(c, weight=1)

        def _make_single_entry(parent, key_for_var):
            var = tk.StringVar()
            e = ttk.Entry(parent, textvariable=var)
            e.pack(fill="x", expand=True)
            self.form_inputs[key_for_var] = var

        def _make_split_cell(parent, combined_key):
            """
            Inside one cell: [EntryL]   @ right_key:   [EntryR]
            - Outer label uses the left part of the combined key.
            - We store **unique internal keys** for left/right to avoid collisions when
            two different combined keys share the same left key text.
            """
            left_key, right_key = combined_key.split(" @ ", 1)

            # Use unique internal names tied to the combined column
            left_internal  = f"{combined_key}::L"
            right_internal = f"{combined_key}::R"

            # at_join_map maps the combined CSV column -> (internal_left, internal_right)
            self.at_join_map[combined_key] = (left_internal, right_internal)

            wrap = ttk.Frame(parent)
            wrap.pack(fill="x", expand=True)

            wrap.columnconfigure(0, weight=1)
            wrap.columnconfigure(3, weight=1)

            # Left entry (no sublabel)
            var_l = tk.StringVar()
            ttk.Entry(wrap, textvariable=var_l).grid(row=0, column=0, sticky="we", padx=(0, 6))
            self.form_inputs[left_internal] = var_l  # <-- store by internal key

            # '@' and right sublabel
            ttk.Label(wrap, text="@").grid(row=0, column=1, sticky="w", padx=(0, 6))
            ttk.Label(wrap, text=f"{right_key}:").grid(row=0, column=2, sticky="e", padx=(0, 6))

            # Right entry
            var_r = tk.StringVar()
            ttk.Entry(wrap, textvariable=var_r).grid(row=0, column=3, sticky="we")
            self.form_inputs[right_internal] = var_r  # <-- store by internal key


        def _place_side(row, label_col, cell_col, key):
            # Decide label text and widget
            if " @ " in key:
                left_key, right_key = key.split(" @ ", 1)
                label_txt = f"{left_key}:"
                ttk.Label(self.dynamic_frame, text=label_txt).grid(
                    row=row, column=label_col, sticky="e", padx=6, pady=4
                )
                cell = ttk.Frame(self.dynamic_frame)
                cell.grid(row=row, column=cell_col, sticky="we", padx=(0, 8))
                _make_split_cell(cell, key)
            else:
                ttk.Label(self.dynamic_frame, text=f"{key}:").grid(
                    row=row, column=label_col, sticky="e", padx=6, pady=4
                )
                cell = ttk.Frame(self.dynamic_frame)
                cell.grid(row=row, column=cell_col, sticky="we", padx=(0, 8))
                _make_single_entry(cell, key)

        # Render two columns per row
        r = 0
        i = 0
        while i < len(columns):
            left_key = columns[i]
            _place_side(r, 0, 1, left_key)

            # spacer between left and right halves
            ttk.Label(self.dynamic_frame, text="").grid(row=r, column=2, padx=4)

            if i + 1 < len(columns):
                right_key = columns[i + 1]
                _place_side(r, 3, 4, right_key)

            r += 1
            i += 2



    def _compute_ordered_columns(self, template_fields):
        head = ["MPN", "Quantity", "Value"]
        middle = [f for f in template_fields if f not in ID_FIELDS]
        desc_present = "Description" in middle
        data_present = "Datasheet" in middle
        middle = [f for f in middle if f not in ("Description", "Datasheet")]

        ordered = head + middle
        ordered.append("Description" if desc_present else "Description")
        ordered.append("Datasheet")
        ordered += ID_FIELDS

        seen, result = set(), []
        for c in ordered:
            if c not in seen:
                seen.add(c)
                result.append(c)
        return result

    def _populate_tt(self):
        self._tt_label_to_code.clear()
        for tt_code, tt_name in self.schema.domains.items():
            self._tt_label_to_code[tt_name] = tt_code
        labels = list(self._tt_label_to_code.keys())
        self.tt_cb["values"] = labels
        if labels:
            self.tt_cb.set(labels[0])
            self.on_tt_change()

    def on_tt_change(self, event=None):
        tt_label = self.tt_cb.get()
        tt_code = self._tt_label_to_code.get(tt_label, "")

        self._ff_label_to_code.clear()
        families = self.schema.get_families(tt_code)
        for ff_code, ff_name in families.items():
            self._ff_label_to_code[ff_name] = ff_code
        ff_labels = list(self._ff_label_to_code.keys()) or ["(unspecified)"]
        self.ff_cb["values"] = ff_labels
        self.ff_cb.set(ff_labels[0])

        self.on_ff_change()

    def on_ff_change(self, event=None):
        """
        Respond to Family change:
        - Rebuild CC/SS combos
        - Re-render dynamic form for the TTFF template
        - Recompute column order and refresh the table safely
        """
        tt_label = self.tt_cb.get()
        tt_code = self._tt_label_to_code.get(tt_label, "")

        ff_label = self.ff_cb.get()
        ff_code = self._ff_label_to_code.get(ff_label, "")

        # CC
        self._cc_label_to_code.clear()
        cc_map = self.schema.get_cc(tt_code, ff_code)
        if cc_map:
            labels = []
            for cc_code, cc_name in cc_map.items():
                self._cc_label_to_code[cc_name] = cc_code
                labels.append(cc_name)
            self.cc_cb["values"] = labels
            self.cc_cb.set(labels[0] if labels else "")
        else:
            self._cc_label_to_code["(unspecified)"] = "00"
            self.cc_cb["values"] = ["(unspecified)"]
            self.cc_cb.set("(unspecified)")

        # SS
        self._ss_label_to_code.clear()
        ss_map = self.schema.get_ss(tt_code, ff_code)
        if ss_map:
            labels = []
            for ss_code, ss_name in ss_map.items():
                self._ss_label_to_code[ss_name] = ss_code
                labels.append(ss_name)
            self.ss_cb["values"] = labels
            self.ss_cb.set(labels[0] if labels else "")
        else:
            self._ss_label_to_code["(unspecified)"] = "00"
            self.ss_cb["values"] = ["(unspecified)"]
            self.ss_cb.set("(unspecified)")

        # Template fields for this TTFF
        fields_for_ttff = self._get_active_template_fields(tt_code, ff_code)

        # Re-render dynamic form (ID fields excluded)
        self._render_dynamic_fields(fields_for_ttff)

        # Update strict column order and apply to model
        ordered_cols = self._compute_ordered_columns(fields_for_ttff)
        self.model.set_active_order(ordered_cols)

        # Safely refresh table (rebuild headings, repopulate, autosize)
        self._refresh_table()

    def _insert_tree_row(self, row, iid=None):
        """
        Insert a visual row using current active order.
        We set the Treeview item id (iid) to the row index for stable mapping.
        """
        values = [row.get(c, "") for c in self.model.active_order]
        if iid is None:
            iid = str(len(self.tree.get_children()))
        self.tree.insert("", "end", iid=iid, values=values)

    def _refresh_table(self):
        """
        Recreate the table for the current active_order and repopulate all rows.
        Protects against column mismatches by rebuilding headings before insert.
        """
        # Always rebuild to keep columns in sync with self.model.active_order
        self._build_table()

        # Insert all rows using the current order
        for idx, r in enumerate(self.model.rows):
            values = [r.get(c, "") for c in self.model.active_order]
            self.tree.insert("", "end", iid=str(idx), values=values)

        # Autosize after population
        self._auto_size_columns()

    def _auto_size_columns(self, min_px: int = 96, max_px: int = 640, pad_px: int = 28):
        """
        Robust autosizer with guards:
        - Skips any column not currently present in the Treeview (prevents
        'Invalid column index' errors when templates switch).
        - Uses font metrics for header + cells.
        - Enforces a minimum width so columns never collapse.
        """
        import tkinter.font as tkfont

        try:
            self.update_idletasks()
        except Exception:
            pass

        if not hasattr(self, "tree"):
            return

        tree_cols = set(self.tree["columns"])
        fnt = tkfont.nametofont("TkDefaultFont")

        for col in self.model.active_order:
            if col not in tree_cols:
                # Column not in the current Treeview (different template) — skip
                continue

            # Start with header width
            maxw = fnt.measure(col)

            # Include all cell values
            for iid in self.tree.get_children():
                txt = str(self.tree.set(iid, col))
                w = fnt.measure(txt)
                if w > maxw:
                    maxw = w

            width = max(min_px, min(maxw + pad_px, max_px))
            self.tree.column(col, width=width, minwidth=min_px, stretch=True)

    def on_tree_double_click(self, event):
        """
        Load the double-clicked row back into the edit form for update.
        Sets self._editing_index to the row index; saving will update in-place without new DMTUID.
        """
        item = self.tree.identify_row(event.y)
        if not item:
            return
        try:
            row_index = int(item)
        except ValueError:
            # Fallback: compute by order
            row_index = self.tree.index(item)
        if row_index < 0 or row_index >= len(self.model.rows):
            return
        self._editing_index = row_index
        row = self.model.rows[row_index]
        self._load_row_into_form(row)
        self.status_var.set(f"Editing row #{row_index + 1}  ({row.get('DMTUID','')})")

    def _load_row_into_form(self, row: dict):
        """
        Load a CSV row to the form:
        1) Re-select TT/FF/CC/SS to match row codes.
        2) Re-render the dynamic form for that TTFF template.
        3) Populate inputs (split '@' fields included).
        """
        if not isinstance(row, dict):
            return

        # --- 1) Decode row codes
        tt_code = str(row.get("TT", "") or "").zfill(2)
        ff_code = str(row.get("FF", "") or "").zfill(2)
        cc_code = str(row.get("CC", "") or "").zfill(2)
        ss_code = str(row.get("SS", "") or "").zfill(2)

        # TT
        if tt_code in self.schema.domains:
            for lbl, code in self._tt_label_to_code.items():
                if code == tt_code:
                    self.tt_cb.set(lbl)
                    break

        # Rebuild FF choices for this TT and select by code
        families = self.schema.get_families(tt_code)
        self._ff_label_to_code.clear()
        if families:
            ff_labels, ff_sel = [], None
            for ff, name in families.items():
                self._ff_label_to_code[name] = ff
                ff_labels.append(name)
                if ff == ff_code:
                    ff_sel = name
            self.ff_cb["values"] = ff_labels
            self.ff_cb.set(ff_sel or (ff_labels[0] if ff_labels else ""))
        else:
            self.ff_cb["values"] = ["(unspecified)"]
            self.ff_cb.set("(unspecified)")
            self._ff_label_to_code["(unspecified)"] = "00"

        # Rebuild CC for TT/FF
        self._cc_label_to_code.clear()
        cc_map = self.schema.get_cc(tt_code, ff_code)
        if cc_map:
            cc_labels, cc_sel = [], None
            for cc, name in cc_map.items():
                self._cc_label_to_code[name] = cc
                cc_labels.append(name)
                if cc == cc_code:
                    cc_sel = name
            self.cc_cb["values"] = cc_labels
            self.cc_cb.set(cc_sel or (cc_labels[0] if cc_labels else ""))
        else:
            self.cc_cb["values"] = ["(unspecified)"]
            self.cc_cb.set("(unspecified)")
            self._cc_label_to_code["(unspecified)"] = "00"

        # Rebuild SS for TT/FF
        self._ss_label_to_code.clear()
        ss_map = self.schema.get_ss(tt_code, ff_code)
        if ss_map:
            ss_labels, ss_sel = [], None
            for ss, name in ss_map.items():
                self._ss_label_to_code[name] = ss
                ss_labels.append(name)
                if ss == ss_code:
                    ss_sel = name
            self.ss_cb["values"] = ss_labels
            self.ss_cb.set(ss_sel or (ss_labels[0] if ss_labels else ""))
        else:
            self.ss_cb["values"] = ["(unspecified)"]
            self.ss_cb.set("(unspecified)")
            self._ss_label_to_code["(unspecified)"] = "00"

        # --- 2) Re-render the dynamic form to the proper TTFF template
        fields_for_ttff = self._get_active_template_fields(tt_code, ff_code)
        self._render_dynamic_fields(fields_for_ttff)

        # Update table columns order to this template
        ordered_cols = self._compute_ordered_columns(fields_for_ttff)
        self.model.set_active_order(ordered_cols)
        if hasattr(self, "table_frame") and self.table_frame.winfo_exists():
            self._refresh_table()  # rebuild with new header/cols
        self._auto_size_columns()

        # --- 3) Populate inputs
        # Fill split '@' first
        for combined, (left_key_internal, right_key_internal) in getattr(self, "at_join_map", {}).items():
            v = row.get(combined, "")
            if not isinstance(v, str):
                v = "" if v is None else str(v)

            lv, rv = "", ""

            s = v.strip()
            if s:
                if "@" in s:
                    # canonical: "300 mA @ 100 kHz"
                    parts = [p.strip() for p in s.split("@", 1)]
                    lv = parts[0]
                    rv = parts[1] if len(parts) == 2 else ""
                else:
                    # tolerant fallbacks:
                    # 1) try trailing frequency (e.g., "300 mA 100 kHz")
                    m = re.search(r"(\d[\d.,]*\s*(?:[GMk]?Hz))\s*$", s, flags=re.IGNORECASE)
                    if m:
                        rv = m.group(1).strip()
                        lv = s[:m.start()].strip()
                    else:
                        # 2) comma separated? "300 mA, 100 kHz"
                        if "," in s:
                            a, b = s.split(",", 1)
                            lv, rv = a.strip(), b.strip()
                        else:
                            # 3) nothing to split -> put everything on the left
                            lv, rv = s, ""

            # Optional normalization exactly like your previous code (kept behavior)
            if self._should_normalize_field(left_key_internal):
                lv = self._normalize_units(lv)
            if self._should_normalize_field(right_key_internal):
                rv = self._normalize_units(rv)

            if left_key_internal in self.form_inputs:
                self.form_inputs[left_key_internal].set(lv)
            if right_key_internal in self.form_inputs:
                self.form_inputs[right_key_internal].set(rv)

        # Now fill simple fields
        subkeys = set()
        for _, (lk, rk) in getattr(self, "at_join_map", {}).items():
            subkeys.add(lk); subkeys.add(rk)

        for k, var in self.form_inputs.items():
            if k in subkeys:
                continue
            val = row.get(k, "")
            if val is None:
                val = ""
            if self._should_normalize_field(k):
                val = self._normalize_units(str(val))
            var.set(str(val))


    def on_open_csv(self):
        initial = (
            self.model.csv_path
            or self.app_config.get("last_csv")
            or os.path.join(os.getcwd(), "dmt_items.csv")
        )
        path = filedialog.asksaveasfilename(
            title="Choose or create CSV…",
            initialfile=os.path.basename(initial),
            initialdir=os.path.dirname(initial),
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not path:
            return False

        if os.path.exists(path):
            self.model.load(path)
        else:
            self.model.csv_path = path
            self.model.rows = []
            self.model.index.clear()
            try:
                self.model.save(path=path, field_order=self.model.active_order)
            except Exception:
                write_csv_rows(path, self.model.active_order, [])

        self._build_table()
        for r in self.model.rows:
            self.tree.insert(
                "", "end", values=[r.get(c, "") for c in self.model.active_order]
            )

        self.app_config["last_csv"] = path
        write_json_safe(self.config_path, self.app_config)
        self.status_var.set(f"CSV: {path}")
        return True

    def on_save_as(self):
        path = filedialog.asksaveasfilename(
            title="Save CSV As…",
            initialfile=os.path.basename(self.model.csv_path or "dmt_items.csv"),
            initialdir=(
                os.path.dirname(self.model.csv_path)
                if self.model.csv_path
                else os.getcwd()
            ),
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            write_csv_rows(path, self.model.active_order, self.model.rows)
            self.model.csv_path = path
            self.app_config["last_csv"] = path
            write_json_safe(self.config_path, self.app_config)
            self.status_var.set(f"Saved: {path}")
            messagebox.showinfo(APP_NAME, f"Saved:\n{path}")
        except Exception as e:
            messagebox.showerror(APP_NAME, f"Save As failed:\n{e}")

    # --------------------- field defs ---------------------

    def _load_field_defs(self):
        """
        Field definitions WITHOUT dmt_fields.json.
        - Core ID columns are fixed.
        - The per-family, per-TTFF field list always comes from dmt_templates.json
        (loaded by _load_templates and then expanded at runtime by _expand_template_fields).
        - We keep a minimal set of generic columns so the CSV has a stable seed header,
        but the active columns used by the table/CSV ultimately come from templates.
        - Do NOT change crucial data in dmt_templates.json; we only transform at runtime.
        """

        # 1) Core ID columns (fixed)
        self.core_fields = [
            {"key": "TT", "label": "TT"},
            {"key": "FF", "label": "FF"},
            {"key": "CC", "label": "CC"},
            {"key": "SS", "label": "SS"},
            {"key": "XXX", "label": "XXX"},
            {"key": "DMTUID", "label": "DMTUID"},
        ]

        # 2) Minimal generic text columns that are commonly present across templates.
        #    These just seed the CSV header; actual visible columns come from the selected template.
        generic_text = [
            {"key": "MPN", "label": "MPN"},
            {
                "key": "Quantity",
                "label": "Quantity",
            },  # you fill this manually; AI never overwrites it
            {"key": "Value", "label": "Value"},
            {"key": "Description", "label": "Description"},
            {"key": "Datasheet", "label": "Datasheet"},
            {"key": "RoHS", "label": "RoHS"},
        ]

        # 3) Compose the seed CSV header (order here is only a fallback;
        #    the real order is computed later by _compute_ordered_columns based on the template)
        self.csv_fields = [f["key"] for f in self.core_fields] + [
            f["key"] for f in generic_text
        ]

        # 4) Human labels for the seed set (templates contribute their own labels by using the exact text as keys)
        self.field_labels = {
            **{f["key"]: f["label"] for f in self.core_fields},
            **{f["key"]: f["label"] for f in generic_text},
        }

        # 5) Form field order here is only for static extras; the dynamic form comes from templates.
        #    We keep it empty so the UI is entirely driven by the selected TT/FF template.
        self.form_field_order = []

    # --------------------- PDF download + OCR ---------------------

    def _download_pdf(self, url: str, target_dir: str, filename: str) -> str:
        import requests

        r = requests.get(url, stream=True, timeout=60)
        r.raise_for_status()
        pdf_path = os.path.join(target_dir, filename)
        with open(pdf_path, "wb") as f:
            for chunk in r.iter_content(1 << 14):
                if chunk:
                    f.write(chunk)
        return pdf_path

    def _pdf_to_pages(
        self, path: str, force_ocr: bool = False, dpi: int = 350, debug_dir: str = None
    ):
        """
        MASTER extractor: prefer PyMuPDF (fitz). If unavailable / broken, fallback to pdfminer.six.
        OCR is intentionally disabled. Returns list[{"text": str, "tables": list}].
        """
        # 1) Try PyMuPDF
        try:
            pages = self._pdf_to_pages_text_tables_structured(path)
            if pages and any((p.get("text") or "").strip() for p in pages):
                return pages
            self._dbg("PyMuPDF returned empty text; will try pdfminer.six fallback.")
        except Exception as e:
            self._dbg(f"Structured extractor failed: {e}")

        # 2) Fallback: pdfminer.six
        try:
            pages = self._pdf_to_pages_text_tables_pdfminer(path)
            if pages and any((p.get("text") or "").strip() for p in pages):
                return pages
            raise RuntimeError("pdfminer.six produced no text.")
        except Exception as e:
            self._dbg(f"pdfminer fallback failed: {e}")

        # 3) Final: give up (do NOT OCR)
        raise RuntimeError("No text extracted from PDF via PyMuPDF/pdfminer.")

    def _pdf_to_pages_text_tables_pdfminer(self, path: str):
        """
        Pure-Python fallback using pdfminer.six to extract per-page text without OCR.
        - Requires: pip install pdfminer.six
        - Returns: [{"text": <page_text>, "tables": []}, ...]
        """
        from pdfminer.high_level import extract_pages
        from pdfminer.layout import LTTextContainer, LTTextLine, LTAnno

        pages = []
        # iterate layout pages; accumulate visible text in approximate reading order
        for page_layout in extract_pages(path):
            lines = []
            for element in page_layout:
                if isinstance(element, LTTextContainer):
                    for text_line in element:
                        if isinstance(text_line, LTTextLine):
                            s = text_line.get_text()
                            if s:
                                lines.append(s.rstrip("\n"))
            page_text = "\n".join(lines)
            # normalize NBSP and collapse stray whitespace a little
            page_text = (page_text or "").replace("\u00a0", " ")
            pages.append({"text": page_text, "tables": []})
        return pages

    def _pdf_to_pages_text_tables_structured(self, path: str):
        """
        PyMuPDF-based extractor.
        - Requires: pip install pymupdf
        - Returns: [{"text": <page_text>, "tables": []}, ...]
        Notes:
        - We normalize NBSP to spaces to reduce false negatives in header detection.
        - If the import fails with a 'frontend' message, it's almost always a broken wheel
        or a local name conflict (e.g., a local file called 'fitz.py'). Reinstall pymupdf.
        """
        try:
            import fitz  # PyMuPDF
        except Exception as imp_err:
            # Surface a helpful message upward so _pdf_to_pages can report it and try pdfminer.
            raise RuntimeError(
                f"PyMuPDF import failed: {imp_err}. Reinstall with 'pip install --upgrade pymupdf' and ensure no local fitz.py shadows it."
            )

        pages = []
        with fitz.open(path) as doc:
            for i in range(doc.page_count):
                pg = doc.load_page(i)
                # 'text' gives reading-order text which works best for section/heading detection
                txt = pg.get_text("text") or ""
                txt = txt.replace("\u00a0", " ")  # NBSP → space
                pages.append({"text": txt, "tables": []})
        return pages

    def _pdf_to_pages_ocr(self, path: str, dpi: int = 350, debug_dir: str = None):
        from pdf2image import convert_from_path
        import pytesseract

        pil_pages = convert_from_path(path, dpi=dpi)
        out = []

        for idx, img in enumerate(pil_pages, 1):
            if debug_dir:
                img_out = os.path.join(debug_dir, f"page_{idx:03}.png")
                img.save(img_out)

            page_text = pytesseract.image_to_string(img, lang="eng", config="--psm 6")

            tsv_df = pytesseract.image_to_data(
                img,
                lang="eng",
                config="--psm 6",
                output_type=pytesseract.Output.DATAFRAME,
            )

            if debug_dir and tsv_df is not None and len(tsv_df) > 0:
                csv_out = os.path.join(debug_dir, f"page_{idx:03}_tsv.csv")
                try:
                    tsv_df.to_csv(csv_out, index=False)
                except Exception:
                    pass

            tables = self._tesseract_lines_to_tables(tsv_df)
            out.append({"text": page_text or "", "tables": tables})

        return out

    def _tesseract_lines_to_tables(
        self, tsv_df, gap_factor: float = 1.8, min_cols: int = 3
    ):
        import numpy as np
        import pandas as pd

        if tsv_df is None or len(tsv_df) == 0:
            return []

        df = tsv_df.copy()
        df = df[df["text"].astype(str).str.strip() != ""]
        if df.empty:
            return []

        df["line_key"] = list(zip(df["block_num"], df["par_num"], df["line_num"]))

        line_rows = []
        for key, g in df.groupby("line_key"):
            g = g.sort_values("left")
            xs = g["left"].to_numpy()
            words = g["text"].astype(str).tolist()
            if len(words) == 0:
                continue

            gaps = np.diff(xs)
            med = np.median(gaps) if len(gaps) else 0
            threshold = max(12, med * gap_factor)
            row_cells, current = [], []
            current.append(words[0])
            last_x = xs[0]

            for w, x in zip(words[1:], xs[1:]):
                if (x - last_x) > threshold:
                    row_cells.append(" ".join(current).strip())
                    current = [w]
                else:
                    current.append(w)
                last_x = x
            row_cells.append(" ".join(current).strip())
            line_rows.append(row_cells)

        tables, current_tbl = [], []
        for row in line_rows:
            if len(row) >= min_cols:
                current_tbl.append(row)
            else:
                if len(current_tbl) >= 2:
                    tables.append(current_tbl)
                current_tbl = []
        if len(current_tbl) >= 2:
            tables.append(current_tbl)

        return tables

    # --------------------- page filtering (graphs) ---------------------

    def _is_graph_heavy_page(self, page_dict: dict) -> bool:
        """
        Aggressive graph/figure page detector for PyMuPDF text.
        Keeps known spec sections; flags pages dominated by 'fig/figure/curves/vs' vocabulary.
        """
        if not isinstance(page_dict, dict):
            return False

        import re

        text = page_dict.get("text") or ""
        lower = text.lower()

        # Keep-list: if we see any of these, prefer to keep the page
        keep_keywords = (
            "absolute maximum ratings",
            "recommended operating conditions",
            "electrical characteristics",
            "thermal information",
            "thermal characteristics",
            "pin configuration",
            "pin descriptions",
            "pin assignment",
            "ordering information",
            "ordering guide",
            "package information",
            "mechanical data",
            "tape and reel",
            "marking",
            "moisture sensitivity",
            "revision history",
            "features",
            "applications",
            "description",
            "product overview",
            "summary of features",
        )
        if any(k in lower for k in keep_keywords):
            return False

        # Graph-ish vocabulary
        graph_kw = (
            "typical electrical characteristics",
            "typical characteristics",
            "performance characteristics",
            "typical performance",
            "transfer characteristics",
            "output characteristics",
            "safe operating area",
            "soa",
            "figure",
            "fig.",
            "fig ",
            "fig:",
            "curve",
            "curves",
            "graph",
            "plot",
            "hysteresis",
            "waveform",
            "oscilloscope",
            # MOSFET-ish words often on plots:
            "rds(on)",
            "rdson",
            "on-resistance",
            "gate charge",
            "qg",
            "vth",
            "capacitance",
            "ciss",
            "crss",
            "cds",
            "transient thermal impedance",
            "junction temperature",
        )
        hits = sum(1 for k in graph_kw if k in lower)

        # 'vs' patterns (axes)
        vs_hits = len(re.findall(r"\bvs\b|vs\.", lower))
        axes_pairs = len(re.findall(r"\b[a-z]{1,6}\s+vs\.?\s+[a-z]{1,6}\b", lower))

        # Density: figure-heavy pages often contain shorter captions and many 'Figure X' lines
        fig_lines = len(re.findall(r"\bfigure\s+\d+|\bfig\.\s*\d+", lower))
        word_count = len(re.findall(r"\w+", lower))

        # Decision logic
        if fig_lines >= 2 and (hits >= 1 or vs_hits >= 1 or axes_pairs >= 1):
            return True
        if (hits >= 2 and (vs_hits >= 1 or axes_pairs >= 1)) and word_count < 1200:
            return True
        if ("typical" in lower and "characteristics" in lower) and (
            vs_hits >= 1 or fig_lines >= 1
        ):
            return True

        return False

    def _find_graph_section_bounds(self, pages):
        """
        Locate a contiguous 'graph section' (1-based inclusive indices) typically titled
        'Typical (Electrical) Characteristics' starting around page 3, and ending before the
        next hard section such as 'Package Information', 'Ordering Information', etc.
        Returns: (start_index, end_index) or (None, None) if not found.
        """
        import re

        # Configurable: don't consider graph sections before this page (1-based)
        min_graph_start = int(self.app_config.get("min_graph_section_page", 3))

        # Normalize page texts
        norm = []
        for p in pages:
            t = (p.get("text") if isinstance(p, dict) else str(p or "")) or ""
            t = t.replace("\u00a0", " ")
            t = re.sub(r"[ \t]+", " ", t)
            norm.append(t.lower())

        start_hdrs = (
            r"^\s*typical\s+(electrical\s+)?characteristics\b",
            r"^\s*performance\s+characteristics\b",
            r"^\s*transfer\s+characteristics\b",
            r"^\s*output\s+characteristics\b",
            r"^\s*safe\s+operating\s+area\b",
            r"^\s*soa\b",
            r"^\s*device\s+characteristics\b",
        )
        stop_hdrs = (
            r"^\s*package\b",
            r"^\s*package\s+information\b",
            r"^\s*mechanical\b",
            r"^\s*tape\s+and\s+reel\b",
            r"^\s*marking\b",
            r"^\s*ordering\s+information\b",
            r"^\s*moisture\s+sensitivity\b",
            r"^\s*revision\s+history\b",
            r"^\s*absolute\s+maximum\s+ratings\b",
            r"^\s*electrical\s+characteristics\b",
            r"^\s*recommended\s+operating\s+conditions\b",
        )

        # 1) find a plausible start page at/after min_graph_start
        start_idx = None
        for i in range(min_graph_start, len(norm) + 1):
            first_lines = "\n".join(norm[i - 1].splitlines()[:10])
            if any(re.search(rx, first_lines) for rx in start_hdrs):
                start_idx = i
                break

            # fallback: if page has many figure refs near the top, assume graphs start here
            fig_top = len(re.findall(r"\bfigure\s+\d+|\bfig\.\s*\d+", first_lines))
            if fig_top >= 2 and (
                "typical" in first_lines
                or "characteristics" in first_lines
                or "performance" in first_lines
            ):
                start_idx = i
                break

        if start_idx is None:
            return (None, None)

        # 2) end page = previous page before next hard section header
        end_idx = None
        for j in range(start_idx + 1, len(norm) + 1):
            first_lines = "\n".join(norm[j - 1].splitlines()[:10])
            if any(re.search(rx, first_lines) for rx in stop_hdrs):
                end_idx = j - 1
                break

        # 3) fallback extension: advance until pages stop looking graphy
        def looks_graphy(t: str) -> bool:
            return any(
                k in t
                for k in (
                    "typical",
                    "characteristics",
                    "figure",
                    "fig.",
                    "graph",
                    "curves",
                    "soa",
                )
            )

        def looks_keep(t: str) -> bool:
            return any(
                k in t
                for k in (
                    "absolute maximum ratings",
                    "electrical characteristics",
                    "recommended operating conditions",
                    "package",
                    "mechanical",
                    "tape and reel",
                    "marking",
                    "ordering information",
                    "revision history",
                )
            )

        if end_idx is None:
            k = start_idx
            while k < len(norm):
                t = norm[k]
                if looks_keep(t) and not looks_graphy(t):
                    break
                k += 1
            end_idx = k if k > start_idx else len(norm)

        end_idx = max(start_idx, min(end_idx, len(norm)))
        return (start_idx, end_idx)

    def _filter_pages_for_llm(self, pages):
        """
        Filter pipeline:
        A) Cut entire detected graph section (contiguous).
        B) On remaining pages, drop graph-heavy pages per-page.
        C) If too few remain, rescue pages with strong keep sections.
        Returns: (filtered_pages, kept_indices, skipped_indices, total_pages)
        """
        total = len(pages)
        if total == 0:
            return [], [], [], 0

        gs, ge = self._find_graph_section_bounds(pages)
        skip_set = set()
        if gs is not None and ge is not None and 1 <= gs <= ge <= total:
            skip_set.update(range(gs, ge + 1))

        kept_tmp, kept_idx_tmp, skipped_extra = [], [], []
        for i, p in enumerate(pages, 1):
            if i in skip_set:
                continue
            if self._is_graph_heavy_page(p):
                skipped_extra.append(i)
            else:
                kept_tmp.append(p)
                kept_idx_tmp.append(i)

        # Rescue logic if we were too aggressive
        strong_keep = (
            "absolute maximum ratings",
            "electrical characteristics",
            "recommended operating conditions",
            "thermal information",
            "thermal characteristics",
            "pin configuration",
            "pin descriptions",
            "pin assignment",
            "ordering information",
            "package information",
            "mechanical data",
            "tape and reel",
            "marking",
            "moisture sensitivity",
            "revision history",
            "features",
            "description",
            "applications",
            "product overview",
            "summary of features",
        )
        if len(kept_tmp) <= 1:
            for i, p in enumerate(pages, 1):
                if (i in skip_set) or (i in skipped_extra) or (i in kept_idx_tmp):
                    continue
                t = (p.get("text") if isinstance(p, dict) else str(p or "")).lower()
                if any(k in t for k in strong_keep):
                    kept_tmp.append(p)
                    kept_idx_tmp.append(i)

        skipped_idx = sorted(list(skip_set) + skipped_extra)
        return kept_tmp, kept_idx_tmp, skipped_idx, total

    # --------------------- page serialization for LLM ---------------------

    def _serialize_page_for_llm(self, page):
        if isinstance(page, dict):
            text = page.get("text", "") or ""
            tables = page.get("tables") or []
            tbl_lines = []
            for tbl in tables:
                for row in tbl:
                    tbl_lines.append(" | ".join(str(c) for c in row))
                tbl_lines.append("")
            tables_text = ("\nTABLES:\n" + "\n".join(tbl_lines)) if tbl_lines else ""
            return (
                text.strip() + ("\n\n" + tables_text if tables_text else "")
            ).strip()
        return str(page or "")

    # --------------------- Ollama call ---------------------

    def _ollama_extract_page(
        self, host: str, model: str, page_text: str, fields: list
    ) -> dict:
        import requests

        sys_prompt = (
            "You extract fielded data from electronics datasheet pages. "
            "Return ONLY a single JSON object with EXACTLY the requested keys. "
            "For any field not present on this page, return an empty string. "
            "Preserve units/symbols as written (e.g., '±', 'Ω', 'V', 'A', 'mΩ'). "
            "If you reach graph heavy content, return empty strings for all fields. "
            "No prose."
        )

        user_prompt = (
            "DATASHEET PAGE (single page; may not include all fields):\n"
            "--------------------------------------------------------\n"
            f"{page_text}\n\n"
            "Return one JSON object with EXACTLY these keys:\n"
            f"{json.dumps(fields, ensure_ascii=False)}\n"
            'If a value is not found on THIS PAGE, set it to "".\n'
            "JSON only."
            "If you reach graph heavy content, return empty strings for all fields. "
        )

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1,
            "stream": False,
        }

        url = host.rstrip("/") + "/api/chat"
        try:
            r = requests.post(url, json=payload, timeout=180)
            r.raise_for_status()
            jr = r.json()
            content = (jr.get("message") or {}).get("content") or ""
            obj = self._extract_json_object(content)
            if not isinstance(obj, dict):
                self._dbg("Ollama returned non-dict or unparsable JSON for this page.")
                return {}
            clean = {
                k: (
                    obj.get(k) if isinstance(obj.get(k), str) else str(obj.get(k) or "")
                )
                for k in fields
            }
            return clean
        except Exception as e:
            self._dbg(f"Ollama page call failed: {e}")
            return {}

    def _extract_json_object(self, s: str):
        s = s.strip()
        if s.startswith("{") and s.endswith("}"):
            try:
                return json.loads(s)
            except Exception:
                pass
        m = re.search(r"\{.*\}", s, flags=re.DOTALL)
        if not m:
            return {}
        try:
            return json.loads(m.group(0))
        except Exception:
            return {}

    # --------------------- Prefill from PDF (complete) ---------------------

    def on_prefill_from_pdf(self):
        """
        Full pipeline:
        - download PDF → dbdata/<name>/<name>.pdf
        - parse with PyMuPDF
        - filter out graphs/typical characteristics
        - send ONLY kept pages to LLM
        - write mapping + kept/skipped indices
        - delete the downloaded PDF
        """
        from tkinter import simpledialog, messagebox
        import pathlib, json, os

        url = simpledialog.askstring(
            "Datasheet PDF URL", "Paste a direct PDF URL (… .pdf):", parent=self
        )
        if not url:
            return
        url = url.strip()
        if not (url.lower().startswith("http") and url.lower().endswith(".pdf")):
            messagebox.showwarning(
                "Prefill", "Please paste a direct PDF URL ending with .pdf"
            )
            return

        save_debug = bool(self.app_config.get("save_debug_assets", True))
        skip_graphs = bool(self.app_config.get("skip_graph_pages", True))
        base_dir = self.app_config.get("dbdata_dir") or here_path("dbdata")
        ds_name = self._sanitize_ds_name(url)
        ds_dir, dbg_dir = self._ensure_dirs(base_dir, ds_name, save_debug)

        pdf_path = None
        try:
            self._dbg(f"PDF prefill (page-by-page) started. URL={url}")
            pdf_filename = f"{ds_name}.pdf"
            pdf_path = self._download_pdf(url, ds_dir, pdf_filename)
            self._dbg(f"PDF downloaded → {pdf_path}")

            # STRICTLY structured text extraction (PyMuPDF)
            pages = self._pdf_to_pages(pdf_path, force_ocr=False, debug_dir=None)
            total_pages = len(pages)
            if total_pages == 0:
                raise RuntimeError("No text extracted from PDF via PyMuPDF.")

            kept_pages = pages
            kept_idx = list(range(1, total_pages + 1))
            skipped_idx = []

            if skip_graphs:
                kept_pages, kept_idx, skipped_idx, _ = self._filter_pages_for_llm(pages)
                self._dbg(f"Graph filtering: kept={kept_idx} skipped={skipped_idx}")
                self._dbg(
                    f"Pages kept after filtering: {len(kept_pages)}/{total_pages}."
                )
            else:
                self._dbg("Graph filtering disabled by config.")

            # Save the ACTUAL texts we sent to the LLM (for verification)
            if dbg_dir and save_debug:
                pages_dir = os.path.join(dbg_dir, "pages_sent")
                os.makedirs(pages_dir, exist_ok=True)
                for j, p in enumerate(kept_pages, 1):
                    txt = self._serialize_page_for_llm(p)
                    pathlib.Path(
                        os.path.join(pages_dir, f"kept_{j:03}.txt")
                    ).write_text(txt, encoding="utf-8")

            template_fields = list(self.form_inputs.keys())
            self._dbg(f"Template fields (current TT/FF): {template_fields}")

            model = os.environ.get("OLLAMA_MODEL", "gpt-oss:20b")
            host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")

            results = []
            replies_dir = None
            if dbg_dir and save_debug:
                replies_dir = os.path.join(dbg_dir, "ollama_responses")
                os.makedirs(replies_dir, exist_ok=True)

            for i, page in enumerate(kept_pages, 1):
                page_text = self._serialize_page_for_llm(page)
                self._dbg(f"Ollama ask on page {i}/{len(kept_pages)} …")
                resp = self._ollama_extract_page(
                    host, model, page_text, template_fields
                )

                if replies_dir:
                    pathlib.Path(
                        os.path.join(replies_dir, f"resp_{i:03}.json")
                    ).write_text(
                        json.dumps(resp, indent=2, ensure_ascii=False), encoding="utf-8"
                    )

                if isinstance(resp, dict):
                    results.append(resp)
                else:
                    self._dbg(f"Page {i}: non-dict or empty response; ignored.")

            # Merge: later non-empty wins
            merged = {}
            for d in results:
                for k in template_fields:
                    v = (d or {}).get(k)
                    if v not in (None, "", "N/A"):
                        merged[k] = v

            # Mapping report (ALWAYS include kept/skipped indices so you can verify behavior)
            mapping_path = os.path.join(ds_dir, "debug_pdf_mapping.txt")
            lines = []
            lines.append(f"URL: {url}")
            lines.append(f"Model: {model}   Host: {host}")
            lines.append(f"Total pages: {total_pages}")
            if skip_graphs:
                lines.append(f"Pages kept: {len(kept_pages)}  Indices kept: {kept_idx}")
                lines.append(
                    f"Pages skipped: {len(skipped_idx)}  Indices skipped: {skipped_idx}"
                )
            else:
                lines.append("Graph filtering disabled.")
            lines.append("\n---- Final extracted values by field ----")
            for k in template_fields:
                lines.append(f"{k}: {merged.get(k, '')!r}")
            pathlib.Path(mapping_path).write_text("\n".join(lines), encoding="utf-8")
            self._dbg(f"Wrote mapping report → {mapping_path}")

            # Fill the form
            filled = 0
            for k, v in merged.items():
                if k in self.form_inputs and v:
                    self.form_inputs[k].set(v)
                    filled += 1
            self._dbg(
                f"PDF prefill done. Filled {filled}/{len(template_fields)} fields."
            )
            try:
                messagebox.showinfo(
                    "Prefill",
                    f"PDF prefill complete.\nFilled {filled}/{len(template_fields)} fields.",
                )
            except Exception:
                pass

        except Exception as e:
            self._dbg(f"PDF prefill failed: {e}")
            messagebox.showerror("Prefill", f"PDF prefill failed:\n{e}")
        finally:
            # Always delete the downloaded PDF after extraction
            try:
                if pdf_path and os.path.exists(pdf_path):
                    os.remove(pdf_path)
                    self._dbg("Deleted downloaded PDF.")
            except Exception:
                pass

    def _should_normalize_field(self, key: str) -> bool:
        """
        Decide whether a field should have number–unit spacing normalized.
        We EXCLUDE identifiers and texty fields (MPN, Manufacturer, Package, etc.)
        and INCLUDE value/parameter fields where units are expected.
        """
        if not key:
            return False
        k = key.lower()

        # Never normalize these (identifiers / pure text)
        blacklist = {
            "mpn",
            "value",
            "manufacturer",
            "series",
            "package / case",
            "package",
            "supplier device package",
            "mounting type",
            "fet type",
            "technology",
            "grade",
            "qualification",
            "rohs",
            "description",
            "datasheet",
            "value (free text)",
            "value (description)",
            "value (text)",
            "footprint",
            "location",
            "name",
            "notes",
            "quantity",
        }
        if k in blacklist:
            return False

        # Heuristic allow-list by keywords you actually want normalized
        keywords = (
            "volt",
            "current",
            "power",
            "resistance",
            "rds",
            "ohm",
            "Ω",
            "capacit",
            "induct",
            "frequency",
            "slew",
            "gain",
            "bandwidth",
            "psrr",
            "time",
            "delay",
            "jitter",
            "temperature",
            "°c",
            "°f",
            "vgs",
            "vds",
            "vge",
            "vce",
            "id",
            "ic",
            "iit",
            "qg",
            "ciss",
            "crss",
            "coss",
            "esr",
            "dcr",
            "drive voltage",
            "input capacitance",
            "gate charge",
        )
        return any(w in k for w in keywords) or key == "Value"

    def _normalize_units(self, s: str) -> str:
        """
        Idempotent, conservative normalizer:
        - Only inserts a space between a NUMBER and a KNOWN UNIT token.
        - Does NOT touch plain alnum strings like 'STB60NF06LT4' (MPNs).
        - Keeps '15%' intact.
        """
        if not isinstance(s, str) or not s:
            return s

        txt = s

        # Common vendor artifact: ASCII 'Ohm' → Greek Ω (but only as a unit)
        txt = re.sub(r"(?i)(\d)\s*ohm\b", r"\1 Ω", txt)

        # Map of unit patterns we want a space before (after the number)
        # Order from longer to shorter to avoid partial overlaps
        unit_tokens = [
            r"kΩ",
            r"MΩ",
            r"mΩ",
            r"Ω",
            r"kHz",
            r"MHz",
            r"GHz",
            r"Hz",
            r"µs",
            r"us",
            r"ms",
            r"ns",
            r"ps",
            r"s",
            r"°C",
            r"°F",
            r"µA",
            r"uA",
            r"mA",
            r"A",
            r"µV",
            r"uV",
            r"mV",
            r"V",
            r"µW",
            r"uW",
            r"mW",
            r"W",
            r"µF",
            r"uF",
            r"nF",
            r"pF",
            r"mF",
            r"F",
            r"µH",
            r"uH",
            r"nH",
            r"mH",
            r"H",
        ]

        # Space between number and the unit token (avoid percentages)
        unit_alt = "|".join(unit_tokens)
        txt = re.sub(rf"(?<!%)\b(\d[\d.,]*)\s*(?=({unit_alt})\b)", r"\1 ", txt)

        # Normalize spaces around '@' and commas
        txt = re.sub(r"\s*@\s*", " @ ", txt)
        txt = re.sub(r"\s*,\s*", ", ", txt)

        # Collapse multiple spaces
        txt = re.sub(r"[ \t]+", " ", txt).strip()
        return txt

    def on_save_item(self):
        """
        Save handler (merged Add/Save):
        - If editing: update the row in-place (preserve DMTUID/TT/FF/CC/SS).
        - If new: add a row and assign new DMTUID.
        - Only unit-normalize parameter fields; never touch identifiers like MPN.
        """
        # Gather inputs
        values = {k: self.form_inputs[k].get().strip() for k in self.form_inputs}

        # Recombine '@' pairs into their combined CSV column
        for combined, (left_key, right_key) in getattr(self, "at_join_map", {}).items():
            left_v = values.pop(left_key, "").strip()
            right_v = values.pop(right_key, "").strip()
            if self._should_normalize_field(left_key):
                left_v = self._normalize_units(left_v)
            if self._should_normalize_field(right_key):
                right_v = self._normalize_units(right_v)
            values[combined] = (
                f"{left_v} @ {right_v}".strip(" @") if (left_v or right_v) else ""
            )

        # Normalize only eligible scalar fields
        for k in list(values.keys()):
            if isinstance(values[k], str) and self._should_normalize_field(k):
                values[k] = self._normalize_units(values[k])

        # UPDATE existing
        if self._editing_index is not None and 0 <= self._editing_index < len(
            self.model.rows
        ):
            row = self.model.rows[self._editing_index]
            keep_ids = {
                fld: row.get(fld, "")
                for fld in ("TT", "FF", "CC", "SS", "XXX", "DMTUID")
            }
            row.update(values)
            row.update(keep_ids)

            # Update tree row visually
            iid = str(self._editing_index)
            if self.tree.exists(iid):
                for col in self.model.active_order:
                    self.tree.set(iid, col, row.get(col, ""))

            # Save CSV and keep columns sized
            try:
                self.model.save(field_order=self.model.active_order)
                self.status_var.set(
                    f"Updated row #{self._editing_index + 1} ({row.get('DMTUID','')}) and saved."
                )
            except Exception as e:
                messagebox.showerror(APP_NAME, f"Save failed:\n{e}")
                return

            self._editing_index = None
            for var in self.form_inputs.values():
                var.set("")
            self._auto_size_columns()
            return

        # NEW item
        tt_label = self.tt_cb.get()
        ff_label = self.ff_cb.get()
        cc_label = self.cc_cb.get()
        ss_label = self.ss_cb.get()

        tt = (self._tt_label_to_code.get(tt_label, "") or "00").zfill(2)[:2]
        ff = (self._ff_label_to_code.get(ff_label, "") or "00").zfill(2)[:2]
        cc = (self._cc_label_to_code.get(cc_label, "00") or "00").zfill(2)[:2]
        ss = (self._ss_label_to_code.get(ss_label, "00") or "00").zfill(2)[:2]

        if not self.model.csv_path:
            if not self.on_open_csv():
                messagebox.showwarning(APP_NAME, "Choose a CSV file first.")
                return

        row = self.model.add_item({"tt": tt, "ff": ff, "cc": cc, "ss": ss}, values)
        new_index = len(self.model.rows) - 1
        self._insert_tree_row(row, iid=str(new_index))

        try:
            self.model.save(field_order=self.model.active_order)
            self.status_var.set(f"Added {row['DMTUID']} and saved.")
        except Exception as e:
            messagebox.showerror(APP_NAME, f"Save failed:\n{e}")
            return

        for var in self.form_inputs.values():
            var.set("")
        self._auto_size_columns()


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------


def main():
    schema_path = here_path(SCHEMA_FILENAME)
    config_path = here_path(CONFIG_FILENAME)
    root = DMTGUI(schema_path, config_path)
    root.mainloop()


if __name__ == "__main__":
    main()
