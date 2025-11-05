"""
CSV importer for the inventory app.
"""
import os
import csv
import re
import io
import logging
import datetime
import yaml
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Tuple, Optional

from django.conf import settings

from .models import Component, InventoryItem

logger = logging.getLogger(__name__)

# Field mapping from CSV headers to model fields
DEFAULT_FIELD_MAP = {
    "mpn": ["mpn"],
    "manufacturer": ["manufacturer"],
    "value": ["value"],
    "tolerance": ["tolerance"],
    "wattage": ["wattage"],
    "voltage": ["voltage"],
    "current": ["current"],
    "description": ["description"],
    "url_datasheet": ["datasheet", "url_datasheet"],
    # DMT Classification fields
    "dmtuid": ["dmtuid"],
    "dmt_tt": ["tt"],
    "dmt_ff": ["ff"],
    "dmt_cc": ["cc"],
    "dmt_ss": ["ss"],
    "dmt_xxx": ["xxx"],
    # Inventory fields
    "quantity": ["quantity"],
    "storage_location": ["location", "storage_location"],
    "uom": ["uom", "unit of measure"],
    "condition": ["condition"],
    # Special handling for these fields
    "package": ["package", "package name", "package (lxw)", "package / case"],
    "height": ["height", "height - after installation (max.)"],
    # Extra fields that go to the extras JSON
    "resistance": ["resistance"],
    "impedance": ["impedance"],
}


class CSVImporter:
    """
    Importer class for CSV files
    """
    def __init__(self, file_path, dry_run=False, encoding='utf-8', delimiter=','):
        self.file_path = file_path
        self.dry_run = dry_run
        self.encoding = encoding
        self.delimiter = delimiter
        self.results = {
            'created': 0,
            'updated': 0,
            'skipped': 0,
            'errors': 0,
            'error_rows': []
        }
        self.field_map = DEFAULT_FIELD_MAP
        self.categorizer = ComponentCategorizer()
        
    def clean_text(self, value):
        if value is None:
            return ''
        value = str(value)
        value = value.replace('\u00c2\u00b0', '\u00b0').replace('Â°', '°').replace('\u00c2', '')
        value = re.sub(r'[\u2010-\u2015]', '-', value)
        return value.strip()


    def _open_text_with_fallback(self):
        """
        Read file as bytes, handle BOM first (decode as utf-8-sig if present),
        else try declared encoding then fallbacks.
        Returns a StringIO ready to read().
        """
        with open(self.file_path, "rb") as fh:
            data = fh.read()

        # If UTF-8 BOM is present, always decode with utf-8-sig (ignores any 'latin1' hint)
        if data.startswith(b'\xef\xbb\xbf'):
            text = data.decode('utf-8-sig', errors='strict')
            return io.StringIO(text)

        # Build ordered list of encodings to try
        encs = []
        enc_hint = getattr(self, "encoding", None)
        if enc_hint:
            encs.append(enc_hint)
        # try robust defaults
        encs += ["utf-8", "latin1"]

        last_err = None
        for enc in encs:
            try:
                text = data.decode(enc, errors='strict')
                return io.StringIO(text)
            except Exception as e:
                last_err = e
                continue

        # last resort: permissive latin1 so we don't crash
        try:
            text = data.decode("latin1", errors="ignore")
        except Exception:
            raise last_err
        return io.StringIO(text)

    def normalize_string(self, value):
        """
        Normalize a string by removing extra spaces and converting to uppercase
        """
        if not value:
            return value
        value = self.clean_text(value)
        # Remove extra spaces and convert to uppercase
        return re.sub(r'\s+', ' ', value).strip().upper()
    
    def parse_package_dimensions(self, package_str):
        """
        Parse package dimensions from strings like '12.00mm x 12.00mm'
        """
        if not package_str:
            return None, None
        
        # Try to find dimensions in format like "12.00mm x 12.00mm"
        match = re.search(r'(\d+\.?\d*)(?:mm)?\s*[xX]\s*(\d+\.?\d*)(?:mm)?', package_str)
        if match:
            length = Decimal(match.group(1))
            width = Decimal(match.group(2))
            return length, width
        
        return None, None
    
    def parse_height(self, height_str):
        """
        Parse height from strings like '1.2mm'
        """
        if not height_str:
            return None
        
        match = re.search(r'(\d+\.?\d*)(?:mm)?', height_str)
        if match:
            return Decimal(match.group(1))
        
        return None

    def normalize_header(self, header: str) -> str:
        """Lowercase, strip BOM/quotes/space; keep ASCII-only where possible."""
        if header is None:
            return None
        s = str(header)
        s = s.lstrip('\ufeff')            # strip UTF-8 BOM on first header
        s = s.strip().strip('"').strip("'")
        return s.lower()

    def read_csv(self):
        """
        Read the CSV file and yield rows as dictionaries
        - Strips UTF-8 BOM from the first header
        - Case-insensitive header matching
        - Maps known synonyms via self.field_map (e.g. Location -> storage_location)
        - Puts everything else into 'extras' (lowercased keys)
        """
        def norm_header(h):
            if h is None:
                return None
            # strip BOM and whitespace, make lowercase for matching
            return str(h).lstrip('\ufeff').strip()

        with open(self.file_path, 'r', encoding=self.encoding, newline='') as f:
            # Let csv handle both ',' and ';' when delimiter not specified
            reader = csv.DictReader(f, delimiter=self.delimiter)

            # Normalize fieldnames: strip BOM from the first header and lowercase for matching
            raw_headers = reader.fieldnames or []
            norm_headers = [norm_header(h) for h in raw_headers]
            # Rebind DictReader's fieldnames so subsequent rows use normalized headers
            reader.fieldnames = norm_headers

            # Build header_map: csv_header -> model_field (using DEFAULT_FIELD_MAP)
            header_map = {}
            for model_field, csv_headers in self.field_map.items():
                targets = [h.lower() for h in csv_headers]
                for h in norm_headers:
                    if h and h.lower() in targets:
                        header_map[h] = model_field

            for raw_row in reader:
                # keys in raw_row now use normalized headers (lowercased by norm_header)
                mapped = {}
                extras = {}

                # First, copy mapped fields
                for h, v in raw_row.items():
                    key = norm_header(h)
                    # csv can yield None headers for overflow columns; skip them
                    if not key:
                        continue

                    # Coerce value to clean string
                    if isinstance(v, list):
                        v = '; '.join('' if x is None else str(x) for x in v)
                    elif v is None:
                        v = ''
                    else:
                        v = str(v)

                    v = self.clean_text(v)

                    if key in header_map:
                        mf = header_map[key]
                        mapped[mf] = v
                    else:
                        # anything unmapped goes to extras under lowercase key
                        extras[key.lower()] = v

                # Quantity should be numeric if present
                q = mapped.get('quantity') or extras.get('quantity')
                if q is not None and q != '':
                    try:
                        mapped['quantity'] = int(str(q).replace(',', '').strip())
                    except ValueError:
                        # leave it as-is; process_row guards it anyway
                        pass

                # Ensure we have canonical keys for downstream:
                # mpn / manufacturer from either mapped or extras
                mpn_key = 'mpn'
                mfr_key = 'manufacturer'
                if 'mpn' not in mapped:
                    mapped['mpn'] = extras.get('mpn', '')
                if 'manufacturer' not in mapped:
                    mapped['manufacturer'] = extras.get('manufacturer', '')

                # Location -> storage_location (so inventory views work)
                if 'storage_location' not in mapped:
                    loc = extras.get('location')
                    if loc:
                        mapped['storage_location'] = loc

                # Common optional fields often used in UI / models
                for src, dst in [
                    ('datasheet', 'url_datasheet'),
                    ('description', 'description'),
                    ('package', 'package'),  # free-text name; process_row reads as package_name
                    ('value', 'value'),
                    ('dmtuid', 'dmtuid'),
                    ('tt', 'dmt_tt'), ('ff', 'dmt_ff'),
                    ('cc', 'dmt_cc'), ('ss', 'dmt_ss'),
                    ('xxx', 'dmt_xxx'),
                ]:
                    if dst not in mapped and src in extras:
                        mapped[dst] = extras[src]

                if extras:
                    mapped['extras'] = extras

                yield mapped


    def _norm_key(self, s):
        if s is None:
            return ""
        return str(s).lstrip("\ufeff").strip().lower()

    def _get_field(self, row: dict, candidates):
        """
        Look up a logical field across row and row['extras']:
        - handles BOM on keys
        - case-insensitive
        - supports multiple header aliases (candidates: list/tuple)
        Returns cleaned string or "".
        """
        if not candidates:
            return ""
        cand = [self._norm_key(c) for c in candidates]

        # 1) direct keys
        for k, v in row.items():
            if k == "extras":
                continue
            if self._norm_key(k) in cand:
                return self.clean_text(v)

        # 2) extras (already normalized by your read_csv, but be defensive)
        extras = row.get("extras") or {}
        for k, v in extras.items():
            if self._norm_key(k) in cand:
                return self.clean_text(v)

        return ""

    def _get_int(self, row: dict, candidates, default=0):
        s = self._get_field(row, candidates)
        if not s:
            return default
        s = s.replace(",", "").strip()
        try:
            return int(float(s))
        except Exception:
            return default

    def process_row(self, row):
        """
        Process a single row from the CSV, resolving fields from both
        top-level keys and 'extras' with BOM/case/alias tolerance.
        """
        try:
            # Resolve required keys with aliases
            mpn = self._get_field(row, ["mpn", "part number", "mpn/sku"])
            manufacturer = self._get_field(row, ["manufacturer", "mfr", "brand"])
            quantity = self._get_int(row, ["quantity", "qty", "stock"], default=0)

            if not mpn or not manufacturer:
                self.results['skipped'] += 1
                self.results['error_rows'].append({
                    'row': row,
                    'error': "Missing required fields: MPN and Manufacturer"
                })
                return

            mpn_norm = self.normalize_string(mpn)
            manufacturer_norm = self.normalize_string(manufacturer)

            # Optional/common fields (pull from both places)
            value        = self._get_field(row, ["value"])
            tolerance    = self._get_field(row, ["tolerance"])
            wattage      = self._get_field(row, ["wattage"])
            voltage      = self._get_field(row, ["voltage", "voltage - rated"])
            current      = self._get_field(row, ["current", "current - rating", "current - output"])
            description  = self._get_field(row, ["description"])
            url_datasheet= self._get_field(row, ["datasheet", "url_datasheet"])
            dmtuid       = self._get_field(row, ["dmtuid"])
            dmt_tt       = self._get_field(row, ["tt", "dmt_tt"])
            dmt_ff       = self._get_field(row, ["ff", "dmt_ff"])
            dmt_cc       = self._get_field(row, ["cc", "dmt_cc"])
            dmt_ss       = self._get_field(row, ["ss", "dmt_ss"])
            dmt_xxx      = self._get_field(row, ["xxx", "dmt_xxx"])

            # Package/size
            package_name = self._get_field(row, ["package", "package / case", "package/case"])
            package_l_mm = None
            package_w_mm = None
            if package_name:
                L, W = self.parse_package_dimensions(package_name)
                if L and W:
                    package_l_mm, package_w_mm = L, W

            package_h_mm = None
            height_val = self._get_field(row, ["height", "height above board"])
            if height_val:
                package_h_mm = self.parse_height(height_val)

            # Category
            category = self.categorizer.categorize(row)
            category_l1 = category.get('l1', 'Unsorted')
            category_l2 = category.get('l2')

            # Find existing
            component = Component.objects.filter(
                manufacturer_norm=manufacturer_norm,
                mpn_norm=mpn_norm
            ).first()

            if component:
                updated = False
                def _set(field, value):
                    nonlocal updated
                    if value and getattr(component, field) != value:
                        setattr(component, field, value)
                        updated = True

                _set('value', value)
                _set('tolerance', tolerance)
                _set('wattage', wattage)
                _set('voltage', voltage)
                _set('current', current)
                _set('description', description)
                _set('url_datasheet', url_datasheet)
                _set('category_l1', category_l1)
                _set('category_l2', category_l2)
                if package_name and not component.package_name:
                    _set('package_name', package_name)
                if package_l_mm and not component.package_l_mm:
                    _set('package_l_mm', package_l_mm)
                if package_w_mm and not component.package_w_mm:
                    _set('package_w_mm', package_w_mm)
                if package_h_mm and not component.package_h_mm:
                    _set('package_h_mm', package_h_mm)

                # Merge extras
                if row.get('extras'):
                    if not component.extras:
                        component.extras = dict(row['extras'])
                        updated = True
                    else:
                        for k, v in row['extras'].items():
                            if k not in component.extras or not component.extras[k]:
                                component.extras[k] = v
                                updated = True

                if updated and not self.dry_run:
                    component.save()
                    self.results['updated'] += 1
                else:
                    self.results['skipped'] += 1

            else:
                component_data = {
                    'mpn': mpn,
                    'mpn_norm': mpn_norm,
                    'manufacturer': manufacturer,
                    'manufacturer_norm': manufacturer_norm,
                    'value': value,
                    'tolerance': tolerance,
                    'wattage': wattage,
                    'voltage': voltage,
                    'current': current,
                    'package_name': package_name,
                    'package_l_mm': package_l_mm,
                    'package_w_mm': package_w_mm,
                    'package_h_mm': package_h_mm,
                    'description': description,
                    'url_datasheet': url_datasheet,
                    'category_l1': category_l1,
                    'category_l2': category_l2,
                    'dmtuid': dmtuid,
                    'dmt_tt': dmt_tt,
                    'dmt_ff': dmt_ff,
                    'dmt_cc': dmt_cc,
                    'dmt_ss': dmt_ss,
                    'dmt_xxx': dmt_xxx,
                }
                if row.get('extras'):
                    component_data['extras'] = row['extras']

                if not self.dry_run:
                    component = Component.objects.create(**component_data)
                self.results['created'] += 1

            # Inventory
            if not self.dry_run and quantity and quantity > 0 and component:
                try:
                    InventoryItem.objects.create(
                        component=component,
                        quantity=quantity,
                        uom=row.get('uom', 'pcs'),
                        storage_location=row.get('storage_location', 'Unspecified'),
                        condition=row.get('condition', 'new'),
                    )
                except Exception:
                    pass

        except Exception as e:
            self.results['errors'] += 1
            self.results['error_rows'].append({'row': row, 'error': str(e)})

    def save_errors(self):
        """
        Save error rows to a CSV file
        """
        if not self.results['error_rows']:
            return None
        
        # Create directory if it doesn't exist
        error_dir = Path(settings.BASE_DIR) / 'apps' / 'inventory' / 'import_errors'
        os.makedirs(error_dir, exist_ok=True)
        
        # Generate filename with timestamp
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M')
        error_file = error_dir / f'errors_{timestamp}.csv'
        
        # Write errors to CSV
        with open(error_file, 'w', newline='', encoding='utf-8') as csvfile:
            if self.results['error_rows']:
                # Get all field names from the first error row
                fieldnames = list(self.results['error_rows'][0]['row'].keys()) + ['error']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                
                for error_row in self.results['error_rows']:
                    row_data = error_row['row'].copy()
                    row_data['error'] = error_row['error']
                    writer.writerow(row_data)
        
        return error_file
    
    def import_data(self):
        """
        Import data from the CSV file
        """
        for row in self.read_csv():
            self.process_row(row)
        
        if not self.dry_run and self.results['errors'] > 0:
            self.save_errors()
        
        return self.results


class ComponentCategorizer:
    """
    Categorize components based on rules
    """
    def __init__(self):
        self.rules = []
        self.fallback = {'l1': 'Unsorted', 'l2': None}
        self.load_rules()
    
    def load_rules(self):
        """
        Load categorization rules from YAML file
        """
        try:
            rules_path = Path(settings.BASE_DIR) / 'apps' / 'inventory' / 'category_rules.yaml'
            if rules_path.exists():
                with open(rules_path, 'r') as f:
                    data = yaml.safe_load(f)
                    self.rules = data.get('rules', [])
                    self.fallback = data.get('fallback', {'l1': 'Unsorted', 'l2': None})
        except Exception as e:
            logger.error(f"Failed to load category rules: {e}")
    
    def categorize(self, component_data):
        """
        Categorize a component based on the rules
        """
        search_text = ' '.join([
            component_data.get('mpn', ''),
            component_data.get('manufacturer', ''),
            component_data.get('description', ''),
        ]).upper()
        
        for rule in self.rules:
            pattern = rule.get('pattern')
            if pattern and re.search(pattern, search_text):
                return {
                    'l1': rule.get('l1', self.fallback['l1']),
                    'l2': rule.get('l2', self.fallback['l2'])
                }
        
        return self.fallback