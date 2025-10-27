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
import subprocess

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
        self._manual_page_picks = None           # set by dialog to override _resolve_picks
        self._load_ollama_models()               # fill self.ollama_models for the dropdown

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

    def _load_ollama_models(self):
        """
        Prefill available agent names by calling `ollama list`.
        Falls back to a small set if unavailable.
        """
        models = []
        try:
            # Try JSON first
            out = subprocess.check_output(["ollama", "list"], stderr=subprocess.STDOUT, timeout=5)
            text = out.decode("utf-8", errors="ignore").strip()
            # `ollama list` default output is a table; parse first column as model names
            # Example header: NAME    ID    SIZE    MODIFIED
            lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
            if lines and lines[0].lower().startswith("name"):
                for ln in lines[1:]:
                    name = ln.split()[0]
                    if name and name not in models:
                        models.append(name)
            else:
                # best effort: one per line
                for ln in lines:
                    parts = ln.split()
                    if parts:
                        nm = parts[0]
                        if nm and nm not in models:
                            models.append(nm)
        except Exception:
            pass

        if not models:
            models = [
                "mixtral:8x7b",
                "gpt-oss:20b",
                "gemma2:9b",
            ]
        self.ollama_models = models

    def _parse_page_ranges(self, s: str, max_pages: int):
        """
        Parse human page ranges into 0-based indices, clamped to [0, max_pages-1].
        Accepts: '1,2,5-7, 10' -> [0,1,4,5,6,9]
        Empty/invalid -> []
        """
        if not isinstance(s, str):
            return []
        s = s.strip()
        if not s:
            return []

        picks = set()
        for part in s.split(","):
            part = part.strip()
            if not part:
                continue
            if "-" in part:
                a, b = part.split("-", 1)
                try:
                    start = max(1, int(a.strip()))
                    end = max(1, int(b.strip()))
                    if start > end:
                        start, end = end, start
                    for p in range(start, end + 1):
                        if 1 <= p <= max_pages:
                            picks.add(p - 1)
                except Exception:
                    continue
            else:
                try:
                    p = int(part)
                    if 1 <= p <= max_pages:
                        picks.add(p - 1)
                except Exception:
                    continue
        return sorted(picks)

    def _ask_prefill_options(self, default_url: str = "", default_pages: str = "", default_agent: str = "", default_host: str = ""):
        """
        Show a modal dialog that asks for: URL, Pages, Agent, Host.
        Returns dict or None if cancelled.
        """
        dlg = tk.Toplevel(self)
        dlg.title("Prefill Options")
        dlg.transient(self)
        dlg.grab_set()
        dlg.resizable(False, False)

        url_var   = tk.StringVar(value=default_url)
        pages_var = tk.StringVar(value=default_pages)
        agent_var = tk.StringVar(value=default_agent or (self.ollama_models[0] if getattr(self, "ollama_models", []) else "llama3:8b"))
        host_var  = tk.StringVar(value=default_host or os.environ.get("OLLAMA_HOST", "http://localhost:11434"))

        frm = ttk.Frame(dlg, padding=10)
        frm.pack(fill="both", expand=True)

        ttk.Label(frm, text="Datasheet PDF URL:").grid(row=0, column=0, sticky="e", padx=6, pady=6)
        url_entry = ttk.Entry(frm, textvariable=url_var, width=72)
        url_entry.grid(row=0, column=1, sticky="we", padx=6, pady=6)

        ttk.Label(frm, text="Pages (e.g. 1-3,5,9):").grid(row=1, column=0, sticky="e", padx=6, pady=6)
        pages_entry = ttk.Entry(frm, textvariable=pages_var, width=32)
        pages_entry.grid(row=1, column=1, sticky="w", padx=6, pady=6)

        ttk.Label(frm, text="Agent (Ollama model):").grid(row=2, column=0, sticky="e", padx=6, pady=6)
        agent_cb = ttk.Combobox(frm, textvariable=agent_var, values=getattr(self, "ollama_models", []), width=36, state="readonly")
        agent_cb.grid(row=2, column=1, sticky="w", padx=6, pady=6)
        if getattr(self, "ollama_models", []):
            agent_cb.set(agent_var.get())

        ttk.Label(frm, text="Host:").grid(row=3, column=0, sticky="e", padx=6, pady=6)
        host_entry = ttk.Entry(frm, textvariable=host_var, width=36)
        host_entry.grid(row=3, column=1, sticky="w", padx=6, pady=6)

        btns = ttk.Frame(frm)
        btns.grid(row=4, column=0, columnspan=2, sticky="e", pady=(8,0))
        ok = {"clicked": False}
        def on_ok():
            ok["clicked"] = True
            dlg.destroy()
        def on_cancel():
            dlg.destroy()
        ttk.Button(btns, text="Cancel", command=on_cancel).pack(side="right", padx=4)
        ttk.Button(btns, text="OK", command=on_ok).pack(side="right", padx=4)

        frm.columnconfigure(1, weight=1)
        url_entry.focus_set()
        self.wait_window(dlg)

        if not ok["clicked"]:
            return None

        return {
            "url": url_var.get().strip(),
            "pages": pages_var.get().strip(),
            "agent": agent_var.get().strip(),
            "host": host_var.get().strip(),
        }


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
    
    def _resolve_picks(self, path: str):
        """
        Decide which pages to extract:
        - If self._manual_page_picks is set (0-based indices), use it.
        - else: only_5_page=True -> first 5 pages
                only_5_page=False -> smart anchor-based selection
        """
        # Manual override from dialog?
        if isinstance(getattr(self, "_manual_page_picks", None), list) and self._manual_page_picks:
            return list(self._manual_page_picks)

        only_5_page = bool(self.app_config.get("only_5_page", False))
        try:
            import fitz
            with fitz.open(path) as doc:
                if only_5_page:
                    return list(range(min(5, doc.page_count)))
                return self._choose_pages(path, head=5, scan_upto=20)
        except Exception:
            return list(range(5))


    def _pdf_to_pages(self, path: str, force_ocr: bool = False, dpi: int = 350, debug_dir: str = None):
        """
        MASTER extractor with selectable page strategy:
        - self.app_config['page_select'] == 'first5'  -> strict first 5 pages
        - self.app_config['page_select'] == 'smart'   -> head + anchor windows
        Pipeline:
        1) PyMuPDF layout-based text
        2) Tuned pdfminer fallback
        3) OCR if forced or needed
        4) Vector table pass (Camelot) for selected pages
        5) Your existing graph-page filtering
        Returns list[{"text": str, "tables": list[list[str]]}]
        """
        # 0) decide which pages to process
        picks = self._resolve_picks(path)
        if not picks:
            self._dbg("No picks resolved; defaulting to [0..4].")
            picks = list(range(5))

        # 1) PyMuPDF layout first
        pages = []
        try:
            layout_pages = self._pdf_to_pages_text_tables_structured(path)  # returns ALL pages
            pages = [layout_pages[i] for i in picks if i < len(layout_pages)]
        except Exception as e:
            self._dbg(f"Structured extractor failed: {e}")

        # 2) pdfminer fallback if needed
        if not pages or not any((p.get("text") or "").strip() for p in pages):
            try:
                miner_pages = self._pdf_to_pages_text_tables_pdfminer(path)  # returns ALL pages
                pages = [miner_pages[i] for i in picks if i < len(miner_pages)]
            except Exception as e:
                self._dbg(f"pdfminer fallback failed: {e}")

        # 3) OCR if forced or still empty and it's likely scanned/hybrid
        need_ocr = force_ocr or (not any((p.get("text") or "").strip() for p in pages) and self._is_scanned_pdf(path))
        if need_ocr:
            try:
                ocr_pages = self._pdf_to_pages_ocr(path, dpi=dpi, debug_dir=debug_dir)  # returns ALL pages
                pages = [ocr_pages[i] for i in picks if i < len(ocr_pages)]
            except Exception as e:
                self._dbg(f"OCR extractor failed: {e}")

        # 4) Vector-table pass per selected pages
        try:
            if getattr(self, "app_config", {}).get("use_camelot", True):
                page_tables = self._extract_tables_vector(path, target_pages=picks)  # {page_idx: [tables]}
                for local_idx, global_idx in enumerate(picks):
                    if local_idx < len(pages) and page_tables.get(global_idx):
                        pages[local_idx]["tables"].extend(page_tables[global_idx])
        except Exception as e:
            self._dbg(f"Vector table extraction skipped/failed: {e}")

        # 5) Final filtering with your existing logic
        filtered, kept_idx, skipped_idx, total = self._filter_pages_for_llm(pages)
        return filtered

    def _pdf_to_pages_text_tables_pdfminer(self, path: str):
        """
        Tuned pdfminer.six fallback with guarded imports.
        Returns ALL pages; caller will subselect. If pdfminer.six is unavailable, returns [].
        """
        try:
            from pdfminer.high_level import extract_pages
            from pdfminer.layout import LAParams, LTTextContainer, LTTextLine
        except Exception as e:
            self._dbg(f"pdfminer import unavailable/broken: {e}")
            return []

        laparams = LAParams(char_margin=2.0, line_margin=0.4, word_margin=0.1, detect_vertical=False)

        pages = []
        try:
            for _, layout in enumerate(extract_pages(path, laparams=laparams)):
                lines = []
                for el in layout:
                    if isinstance(el, LTTextContainer):
                        for tl in el:
                            if isinstance(tl, LTTextLine):
                                s = tl.get_text()
                                if s:
                                    lines.append(s.rstrip("\n"))
                txt = "\n".join(self._normalize_text(lines))
                txt = self._unit_normalize(txt).replace("\u00a0", " ")
                pages.append({"text": txt, "tables": []})
        except Exception as e:
            self._dbg(f"pdfminer processing failed: {e}")
            return []
        return pages


    def _pdf_to_pages_text_tables_structured(self, path: str):
        """
        PyMuPDF extractor using rawdict (blocks/lines/spans) with light header/footer stripping
        and multi-column ordering. Falls back to pg.get_text('text') if structured pass is thin.
        Returns ALL pages as: [{"text": <page_text>, "tables": []}, ...]
        """
        try:
            import fitz  # PyMuPDF
        except Exception as imp_err:
            raise RuntimeError(
                f"PyMuPDF import failed: {imp_err}. Reinstall with 'pip install --upgrade pymupdf' and ensure no local fitz.py shadows it."
            )

        pages = []
        with fitz.open(path) as doc:
            for i in range(doc.page_count):
                pg = doc.load_page(i)

                # Structured attempt
                txt_struct = ""
                try:
                    rd = pg.get_text("rawdict")
                    blocks = rd.get("blocks", []) if isinstance(rd, dict) else []
                    blocks = self._strip_headers_footers(blocks, pg.rect.height, top_band=36, bottom_band=48)
                    cols = self._group_blocks_into_columns(blocks, min_gap_px=int(getattr(self, "app_config", {}).get("column_gap_px", 40)))

                    lines = []
                    for col in cols:
                        # read order: top→bottom, then left→right inside column
                        for b in sorted(col, key=lambda b: (b["bbox"][1], b["bbox"][0])):
                            for l in b.get("lines", []):
                                spans = [s.get("text", "") for s in l.get("spans", []) if s.get("text", "").strip()]
                                if spans:
                                    lines.append("".join(spans))
                    txt_struct = "\n".join(self._normalize_text(lines))
                except Exception:
                    txt_struct = ""

                # Plain reading-order fallback if structured is too thin
                raw_txt = pg.get_text("text") or ""
                if len((txt_struct or "").strip()) < 40 and raw_txt.strip():
                    txt = raw_txt
                else:
                    txt = txt_struct or raw_txt

                txt = self._unit_normalize((txt or "").replace("\u00a0", " "))
                pages.append({"text": txt, "tables": []})
        return pages



    def _pdf_to_pages(self, path: str, force_ocr: bool = False, dpi: int = 350, debug_dir: str = None):
        """
        MASTER extractor with switchable page strategy (via _resolve_picks / only_5_page).
        Pipeline:
        1) PyMuPDF layout-based text
        2) Tuned pdfminer fallback (if available)
        3) OCR if forced OR if text is still effectively empty (unconditional fallback)
        4) Vector table pass (Camelot) for selected pages
        5) Graph-page filtering
        Returns list[{"text": str, "tables": list[list[str]]}]
        """
        picks = self._resolve_picks(path)
        if not picks:
            picks = list(range(5))

        pages = []

        # 1) PyMuPDF layout first
        try:
            layout_pages = self._pdf_to_pages_text_tables_structured(path)  # returns ALL pages
            pages = [layout_pages[i] for i in picks if i < len(layout_pages)]
        except Exception as e:
            self._dbg(f"Structured extractor failed: {e}")

        def _has_text(plist):
            return bool(plist) and any((p.get("text") or "").strip() for p in plist)

        # 2) pdfminer fallback if needed
        if not _has_text(pages):
            try:
                miner_pages = self._pdf_to_pages_text_tables_pdfminer(path)  # returns ALL pages
                pages = [miner_pages[i] for i in picks if i < len(miner_pages)]
            except Exception as e:
                self._dbg(f"pdfminer fallback failed: {e}")

        # 3) OCR if forced OR still no text (unconditional safety net)
        if force_ocr or not _has_text(pages):
            try:
                ocr_pages = self._pdf_to_pages_ocr(path, dpi=dpi, debug_dir=debug_dir)  # returns ALL pages
                pages = [ocr_pages[i] for i in picks if i < len(ocr_pages)]
            except Exception as e:
                self._dbg(f"OCR extractor failed: {e}")

        # 4) Vector-table pass per selected pages
        try:
            page_tables = self._extract_tables_vector(path, target_pages=picks)  # {page_idx: [tables]}
            for local_idx, global_idx in enumerate(picks):
                if local_idx < len(pages) and page_tables.get(global_idx):
                    pages[local_idx]["tables"].extend(page_tables[global_idx])
        except Exception as e:
            self._dbg(f"Vector table extraction failed: {e}")

        # 5) Final filtering with your existing logic
        filtered, kept_idx, skipped_idx, total = self._filter_pages_for_llm(pages)
        return filtered



    def _pdf_to_pages_ocr(self, path: str, dpi: int = 350, debug_dir: str = None):
        """
        OCR extractor for scanned/hybrid PDFs.
        Honors app_config 'ocr_langs' (default ['eng']) and returns ALL pages.
        """
        from pdf2image import convert_from_path
        import pytesseract
        import os

        ocr_langs = getattr(self, "app_config", {}).get("ocr_langs", ["eng"])
        lang = "+".join(ocr_langs) if ocr_langs else "eng"

        pil_pages = convert_from_path(path, dpi=dpi)
        out = []

        for idx, img in enumerate(pil_pages, 1):
            if debug_dir:
                try:
                    os.makedirs(debug_dir, exist_ok=True)
                    img_out = os.path.join(debug_dir, f"page_{idx:03}.png")
                    img.save(img_out)
                except Exception:
                    pass

            page_text = pytesseract.image_to_string(img, lang=lang, config="--psm 6")
            tsv_df = pytesseract.image_to_data(
                img, lang=lang, config="--psm 6", output_type=pytesseract.Output.DATAFRAME
            )

            if debug_dir and tsv_df is not None and len(tsv_df) > 0:
                csv_out = os.path.join(debug_dir, f"page_{idx:03}_tsv.csv")
                try:
                    tsv_df.to_csv(csv_out, index=False)
                except Exception:
                    pass

            tables = self._tesseract_lines_to_tables(tsv_df)
            txt = "\n".join(self._normalize_text([page_text or ""]))
            txt = self._unit_normalize(txt)
            out.append({"text": txt, "tables": tables})

        return out


    def _tesseract_lines_to_tables(self, tsv_df, gap_factor: float = 1.8, min_cols: int = 3):
        """
        Group OCR words into rows by detecting large x-gaps, then aggregate rows
        into simple tables when enough columns appear consecutively.
        """
        import numpy as np
        import pandas as pd

        if tsv_df is None or len(tsv_df) == 0:
            return []

        df = tsv_df.copy()
        # keep only confident, non-empty words
        if "conf" in df.columns:
            df = df[df["conf"].fillna(-1) >= 0]
        df["text"] = df["text"].astype(str)
        df = df[df["text"].str.strip() != ""]
        if df.empty:
            return []

        # Build a key per OCR line
        key_cols = [c for c in ("block_num", "par_num", "line_num") if c in df.columns]
        if not key_cols:
            return []

        df["line_key"] = list(zip(*[df[k] for k in key_cols]))
        line_rows = []

        for key, g in df.groupby("line_key"):
            g = g.sort_values("left")
            xs = g["left"].to_numpy()
            words = g["text"].astype(str).tolist()
            if not words:
                continue

            gaps = np.diff(xs) if len(xs) > 1 else np.array([])
            med = float(np.median(gaps)) if len(gaps) else 0.0
            threshold = max(12.0, med * float(gap_factor))
            row_cells, current = [], []
            last_x = xs[0] if len(xs) else 0.0

            current.append(words[0])
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
            if len(row) >= int(min_cols):
                current_tbl.append(row)
            else:
                if len(current_tbl) >= 2:
                    tables.append(current_tbl)
                current_tbl = []
        if len(current_tbl) >= 2:
            tables.append(current_tbl)

        return tables

    def _choose_pages(self, path: str, head: int = 5, scan_upto: int = 20):
        """
        Return a sorted list of page indices: first 'head' pages plus a small window
        around important anchor sections found within the first 'scan_upto' pages.
        """
        import fitz
        anchors = (
            "absolute maximum ratings",
            "electrical characteristics",
            "recommended operating conditions",
            "pin configuration",
            "pin descriptions",
            "pin assignment",
            "ordering information",
            "package information",
        )
        picks = set()
        with fitz.open(path) as doc:
            head = max(0, int(head))
            scan_upto = min(int(scan_upto), doc.page_count)
            for i in range(min(head, doc.page_count)):
                picks.add(i)
            for i in range(scan_upto):
                t = (doc.load_page(i).get_text("text") or "").lower()
                if any(a in t for a in anchors):
                    for j in (i - 1, i, i + 1, i + 2):
                        if 0 <= j < doc.page_count:
                            picks.add(j)
        return sorted(picks)

    def _is_scanned_pdf(self, path: str, sample_pages: int = 3) -> bool:
        """
        Heuristic: pages with almost no selectable text but with embedded images.
        """
        import fitz
        img_pages = 0
        with fitz.open(path) as doc:
            for i in range(min(int(sample_pages), doc.page_count)):
                pg = doc.load_page(i)
                has_text = bool((pg.get_text("text") or "").strip())
                has_imgs = bool(pg.get_images(full=True))
                if (not has_text) and has_imgs:
                    img_pages += 1
        return img_pages >= 1

    def _strip_headers_footers(self, blocks, page_height: float, top_band: int = 50, bottom_band: int = 50):
        """
        Remove blocks near top/bottom bands unless they look like important section titles.
        """
        keep_phrases = (
            "absolute maximum ratings",
            "electrical characteristics",
            "recommended operating conditions",
            "pin configuration",
            "ordering information",
            "package information",
        )
        filtered = []
        for b in blocks:
            if "bbox" not in b:
                continue
            x0, y0, x1, y1 = b["bbox"]
            near_top = y0 <= top_band
            near_bottom = y1 >= (page_height - bottom_band)

            text = "".join(
                s.get("text", "")
                for l in b.get("lines", [])
                for s in l.get("spans", [])
            ).strip().lower()

            if (near_top or near_bottom) and text:
                if any(k in text for k in keep_phrases):
                    filtered.append(b)
                # else drop as header/footer
                continue
            filtered.append(b)
        return filtered

    def _group_blocks_into_columns(self, blocks, min_gap_px: int = 40):
        """
        Group blocks into 1..3 columns by detecting big gaps between x-centers.
        No external deps. Returns list of column-lists.
        """
        if not blocks:
            return [[]]

        # compute x-centers
        items = []
        for b in blocks:
            if "bbox" not in b:
                continue
            x0, y0, x1, y1 = b["bbox"]
            xc = (x0 + x1) / 2.0
            items.append((xc, b))
        if not items:
            return [blocks]

        items.sort(key=lambda t: t[0])
        xcs = [t[0] for t in items]

        # find large gaps
        gaps = []
        for i in range(1, len(xcs)):
            gaps.append((xcs[i] - xcs[i - 1], i))
        # pick up to 2 largest gaps that exceed min_gap_px
        big = [g for g in sorted(gaps, reverse=True) if g[0] >= min_gap_px][:2]
        split_indices = sorted([i for _, i in big])

        cols = []
        start = 0
        for idx in split_indices:
            cols.append([b for _, b in items[start:idx]])
            start = idx
        cols.append([b for _, b in items[start:]])
        # ensure left-to-right order
        cols = sorted(cols, key=lambda col: sum((bb["bbox"][0] + bb["bbox"][2]) / 2.0 for bb in col) / max(len(col), 1))
        return cols

    def _normalize_text(self, lines):
        import re, unicodedata
        out = []
        for s in lines:
            s = unicodedata.normalize("NFKC", s).replace("\u00a0", " ")
            s = s.replace("ﬁ", "fi").replace("ﬂ", "fl")
            s = re.sub(r"(\S)-\n(\S)", r"\1\2", s)        # dehyphenate wrapped words
            s = s.replace("\r", "")
            s = re.sub(r"[ \t]+\n", "\n", s)
            out.append(s)
        return out

    def _unit_normalize(self, s: str) -> str:
        # normalize common datasheet glyphs to ASCII
        repl = {
            "Ω": " Ohm",
            "µF": " uF", "µH": " uH", "µA": " uA", "µV": " uV", "µs": " us",
            "°C": " C",
            "±": " +/- ",
        }
        for k, v in repl.items():
            s = s.replace(k, v)
        return s

    def _extract_tables_vector(self, path: str, target_pages):
        """
        Try Camelot lattice on specific pages (vector tables with ruling lines).
        Returns dict: {page_index: [table_rows, ...]}, where table_rows is list[list[str]].
        Silently no-ops if Camelot isn't available.
        """
        out = {}
        try:
            import camelot
        except Exception:
            return out

        # Camelot uses 1-based page numbers; we supply a comma list
        if not target_pages:
            return out
        pages_str = ",".join(str(p + 1) for p in sorted(set(target_pages)))
        try:
            tables = camelot.read_pdf(path, pages=pages_str, flavor="lattice")
        except Exception:
            return out

        # Camelot returns a flat list; map each to its page
        for t in tables:
            try:
                page_1based = int(getattr(t, "page", t.parsing_report.get("page", "1")))
                page_idx = page_1based - 1
                rows = [list(map(str, row)) for row in t.df.values.tolist()]
                if rows:
                    out.setdefault(page_idx, []).append(rows)
            except Exception:
                continue
        return out

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

    def _ollama_extract_page(self, host: str, model: str, page_text: str, fields: list) -> dict:
        import requests, json

        sys_prompt = (
            "You extract fielded data from electronics datasheet pages. "
            "Return ONLY a single JSON object with EXACTLY the requested keys. "
            "For any field not present on this page, return an empty string. "
            "Preserve units/symbols as written (e.g., '±', 'Ω', 'V', 'A', 'mΩ'). "
            "If you reach graph-heavy content, return empty strings for all fields. "
            "No prose."
        )

        if len(page_text) > 12000:
            page_text = page_text[:12000] + " [...]"

        user_prompt = (
            "DATASHEET PAGE (single page; may not include all fields):\n"
            "--------------------------------------------------------\n"
            f"{page_text}\n\n"
            "Return one JSON object with EXACTLY these keys:\n"
            f"{json.dumps(fields, ensure_ascii=False)}\n"
            'If a value is not found on THIS PAGE, set it to "".\n'
            "JSON only."
        )

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1,
            "stream": False,
            "format": "json"
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
                return {k: "" for k in fields}
            return {k: (obj.get(k) if isinstance(obj.get(k), str) else str(obj.get(k) or "")) for k in fields}
        except Exception as e:
            self._dbg(f"Ollama page call failed: {e}")
            return {k: "" for k in fields}

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
        Full pipeline with GUI:
        - popup with URL + Pages + Agent + Host
        - download PDF → dbdata/<name>/<name>.pdf
        - optional manual page override (from dialog)
        - parse & filter
        - ask Ollama page-by-page with chosen agent
        - save debug + fill form
        - delete PDF
        """
        import pathlib, json, os

        # --- 1) Ask options
        default_url = ""
        try:
            clip = self.clipboard_get()
            if isinstance(clip, str) and clip.strip().lower().endswith(".pdf"):
                default_url = clip.strip()
        except Exception:
            pass

        opts = self._ask_prefill_options(
            default_url=default_url,
            default_pages="",
            default_agent=(self.ollama_models[0] if getattr(self, "ollama_models", []) else "llama3:8b"),
            default_host=os.environ.get("OLLAMA_HOST", "http://localhost:11434"),
        )
        if not opts:
            return

        url  = opts["url"]
        if not (url.lower().startswith("http") and url.lower().endswith(".pdf")):
            messagebox.showwarning("Prefill", "Please paste a direct PDF URL ending with .pdf")
            return
        pages_str = opts.get("pages", "")
        chosen_model = opts.get("agent") or "llama3:8b"
        host = opts.get("host") or "http://localhost:11434"

        save_debug = bool(self.app_config.get("save_debug_assets", True))
        skip_graphs = bool(self.app_config.get("skip_graph_pages", True))
        base_dir = self.app_config.get("dbdata_dir") or here_path("dbdata")
        ds_name = self._sanitize_ds_name(url)
        ds_dir, dbg_dir = self._ensure_dirs(base_dir, ds_name, save_debug)

        pdf_path = None
        self._manual_page_picks = None  # reset before run
        try:
            self._dbg(f"PDF prefill (page-by-page) started. URL={url}")
            pdf_filename = f"{ds_name}.pdf"
            pdf_path = self._download_pdf(url, ds_dir, pdf_filename)
            self._dbg(f"PDF downloaded → {pdf_path}")

            # --- 2) If user typed pages, compute 0-based picks with real page count
            try:
                import fitz
                with fitz.open(pdf_path) as doc:
                    max_pages = doc.page_count
                manual = self._parse_page_ranges(pages_str, max_pages) if pages_str else []
                if manual:
                    self._manual_page_picks = manual
                    self._dbg(f"Manual page picks: {[p+1 for p in manual]}")
            except Exception as e:
                self._dbg(f"Manual page parse failed: {e}")

            # --- 3) Extract pages (this will honor self._manual_page_picks if set)
            pages = self._pdf_to_pages(pdf_path, force_ocr=False, debug_dir=None)
            total_pages = len(pages)
            if total_pages == 0:
                raise RuntimeError("No text extracted from PDF via PyMuPDF/pdfminer/OCR.")

            kept_pages = pages
            kept_idx = list(range(1, total_pages + 1))
            skipped_idx = []

            # --- 4) Filter graphs (optional)
            if skip_graphs:
                kept_pages, kept_idx, skipped_idx, _ = self._filter_pages_for_llm(pages)
                self._dbg(f"Graph filtering: kept={kept_idx} skipped={skipped_idx}")
                self._dbg(f"Pages kept after filtering: {len(kept_pages)}/{total_pages}.")
            else:
                self._dbg("Graph filtering disabled by config.")

            # --- 5) Prepare template fields and run Ollama
            template_fields = list(self.form_inputs.keys())
            self._dbg(f"Template fields (current TT/FF): {template_fields}")

            ai_start_time = _dt.now()
            self._dbg(f"Starting AI processing at {ai_start_time.strftime('%H:%M:%S')}")

            results = []
            replies_dir = None
            if dbg_dir and save_debug:
                replies_dir = os.path.join(dbg_dir, "ollama_responses")
                os.makedirs(replies_dir, exist_ok=True)

            for i, page in enumerate(kept_pages, 1):
                page_text = self._serialize_page_for_llm(page)
                self._dbg(f"Ollama ask on page {i}/{len(kept_pages)} …")
                resp = self._ollama_extract_page(host, chosen_model, page_text, template_fields)

                if replies_dir:
                    pathlib.Path(os.path.join(replies_dir, f"resp_{i:03}.json")).write_text(
                        json.dumps(resp, indent=2, ensure_ascii=False), encoding="utf-8"
                    )
                if isinstance(resp, dict):
                    results.append(resp)

            merged = {}
            for d in results:
                for k in template_fields:
                    v = (d or {}).get(k)
                    if v not in (None, "", "N/A"):
                        merged[k] = v

            ai_end_time = _dt.now()
            ai_duration = ai_end_time - ai_start_time
            self._dbg(f"AI processing completed at {ai_end_time.strftime('%H:%M:%S')}")
            self._dbg(f"Total AI processing time: {ai_duration.total_seconds():.2f} seconds")
            self._dbg(f"Used agent: {chosen_model} at host {host}")

            # Mapping report
            mapping_path = os.path.join(ds_dir, "debug_pdf_mapping.txt")
            lines = []
            lines.append(f"URL: {url}")
            lines.append(f"Model: {chosen_model}   Host: {host}")
            lines.append(f"Total pages (post-extraction object): {total_pages}")
            lines.append(f"AI processing time: {ai_duration.total_seconds():.2f} seconds")
            if skip_graphs:
                lines.append(f"Pages kept: {len(kept_pages)}  Indices kept: {kept_idx}")
                lines.append(f"Pages skipped: {len(skipped_idx)}  Indices skipped: {skipped_idx}")
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
            self._dbg(f"PDF prefill done. Filled {filled}/{len(template_fields)} fields.")
            try:
                messagebox.showinfo("Prefill", f"PDF prefill complete.\nFilled {filled}/{len(template_fields)} fields.")
            except Exception:
                pass

        except Exception as e:
            self._dbg(f"PDF prefill failed: {e}")
            messagebox.showerror("Prefill", f"PDF prefill failed:\n{e}")
        finally:
            # Always clear manual override and delete the PDF
            self._manual_page_picks = None
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
