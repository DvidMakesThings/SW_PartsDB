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
        """
        Clean text by fixing encoding issues and normalizing characters.
        Always returns a string (possibly empty).
        """
        if value is None:
            return ""
        if isinstance(value, list):
            value = "; ".join("" if v is None else str(v) for v in value)
        else:
            value = str(value)

        # Fix common encoding issues
        value = value.replace('\u00c2\u00b0', '\u00b0')  # Â° -> °
        value = value.replace('Â°', '°')                # variant
        value = value.replace('\u00c2', '')             # stray Â
        # Normalize various dashes to ASCII hyphen
        value = re.sub(r'[\u2010-\u2015]', '-', value)
        # Strip accidental BOM-as-text at start of a field
        value = re.sub(r'^(?:\ufeff|\u00ef\u00bb\u00bf)', '', value)
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
    
    def read_csv(self):
        """
        Read the CSV file and yield rows as dictionaries:
        - BOM-safe (both true BOM and 'ï»¿' text)
        - auto-detect delimiter (',' vs ';'), override only if needed
        - ignores unnamed/None headers
        - fills 'extras' with normalized columns
        """
        f = self._open_text_with_fallback()

        # Sniff delimiter
        sample = f.read(4096)
        f.seek(0)
        try:
            sniffed = csv.Sniffer().sniff(sample, delimiters=";,")
            dialect = sniffed
        except Exception:
            class _D(csv.Dialect):
                delimiter = ','
                quotechar = '"'
                doublequote = True
                skipinitialspace = True
                lineterminator = '\n'
                quoting = csv.QUOTE_MINIMAL
            dialect = _D

        forced_delim = getattr(self, "delimiter", None)

        def _make_reader(delim=None):
            d = dialect
            if delim:
                d = type("ForcedDialect", (csv.Dialect,), {
                    "delimiter": delim,
                    "quotechar": getattr(dialect, "quotechar", '"'),
                    "doublequote": getattr(dialect, "doublequote", True),
                    "skipinitialspace": getattr(dialect, "skipinitialspace", True),
                    "lineterminator": getattr(dialect, "lineterminator", "\n"),
                    "quoting": getattr(dialect, "quoting", csv.QUOTE_MINIMAL),
                })
            f.seek(0)
            return csv.DictReader(f, dialect=d)

        reader = _make_reader(forced_delim if forced_delim else None)

        # If headers are collapsed, flip delimiter and retry
        def _headers_look_bad(fieldnames):
            if not fieldnames:
                return True
            if len(fieldnames) == 1:
                return True
            h0 = (fieldnames[0] or "")
            return ("," in h0 and ";" in h0)

        if _headers_look_bad(reader.fieldnames):
            alt = ';' if (forced_delim or getattr(dialect, "delimiter", ",")) == ',' else ','
            reader = _make_reader(alt)

        # Normalize header names (strip BOM variants, trim, lower)
        raw_headers = reader.fieldnames or []
        norm_headers = []
        for h in raw_headers:
            if h is None:
                norm_headers.append(None)
                continue
            s = str(h)
            s = re.sub(r'^(?:\ufeff|\u00ef\u00bb\u00bf)', '', s)  # drop BOM or ï»¿
            s = s.strip().lower()
            norm_headers.append(s)

        # Alias map for required fields
        aliases = {
            "mpn": {"mpn", "manufacturer part number", "part number", "pn"},
            "manufacturer": {"manufacturer", "mfr", "maker", "vendor"},
            "quantity": {"qty", "quantity", "count", "stock"},
        }

        def _find_key(target):
            for i, nh in enumerate(norm_headers):
                if nh and nh in aliases[target]:
                    return raw_headers[i]  # original key token used by DictReader rows
            return None

        mpn_key = _find_key("mpn")
        mfr_key = _find_key("manufacturer")
        qty_key = _find_key("quantity")

        for raw_row in reader:
            if raw_row is None:
                continue

            mapped_row = {}
            extras = {}

            # Required fields
            if mpn_key in raw_row:
                mapped_row["mpn"] = self.clean_text(raw_row.get(mpn_key))
            if mfr_key in raw_row:
                mapped_row["manufacturer"] = self.clean_text(self, raw_row.get(mfr_key))
            if qty_key in raw_row:
                q = self.clean_text(self, raw_row.get(qty_key))
                try:
                    mapped_row["quantity"] = int(q) if q else 0
                except Exception:
                    mapped_row["quantity"] = 0

            # Everything else -> extras (normalized)
            for hdr, val in raw_row.items():
                if hdr is None:
                    continue
                nh = re.sub(r'^(?:\ufeff|\u00ef\u00bb\u00bf)', '', str(hdr)).strip().lower()
                if not nh:
                    continue
                if (mpn_key and hdr == mpn_key) or (mfr_key and hdr == mfr_key) or (qty_key and hdr == qty_key):
                    continue

                if isinstance(val, list):
                    val = "; ".join("" if v is None else str(v) for v in val)
                elif val is None:
                    val = ""
                else:
                    val = str(val)

                # If this "header" looks like an entire CSV header line, skip
                if nh.startswith("mpn,") or nh.startswith("ï»¿mpn,") or nh.startswith("\ufeffmpn,"):
                    continue

                extras[nh] = self.clean_text(self, val)

            if extras:
                mapped_row["extras"] = extras

            yield mapped_row

    def process_row(self, row):
        """
        Process a single row from the CSV
        """
        try:
            # Extract and normalize the key fields
            mpn = row.get('mpn')
            manufacturer = row.get('manufacturer')
            
            if not mpn or not manufacturer:
                self.results['skipped'] += 1
                self.results['error_rows'].append({
                    'row': row,
                    'error': "Missing required fields: MPN and Manufacturer"
                })
                return
                
            # Normalize the key fields for consistent lookup
            mpn_norm = self.normalize_string(mpn)
            manufacturer_norm = self.normalize_string(manufacturer)
            
            # Process package dimensions
            package_name = row.get('package')
            package_l_mm = None
            package_w_mm = None
            
            if package_name:
                length, width = self.parse_package_dimensions(package_name)
                if length and width:
                    package_l_mm = length
                    package_w_mm = width
            
            # Process height
            package_h_mm = None
            if 'height' in row:
                package_h_mm = self.parse_height(row.get('height'))
            
            # Assign category
            category = self.categorizer.categorize(row)
            category_l1 = category.get('l1', 'Unsorted')
            category_l2 = category.get('l2')
            
            # Check if component already exists by normalized fields
            component = Component.objects.filter(
                manufacturer_norm=manufacturer_norm,
                mpn_norm=mpn_norm
            ).first()
            
            if component:
                # Update existing component
                updated = False
                for field in ['value', 'tolerance', 'wattage', 'voltage', 'current',
                             'description', 'url_datasheet', 'category_l1', 'category_l2']:
                    if field in row and row[field] and getattr(component, field) != row[field]:
                        setattr(component, field, row[field])
                        updated = True
                
                # Update package info if provided
                if package_name and not component.package_name:
                    component.package_name = package_name
                    updated = True
                
                if package_l_mm and not component.package_l_mm:
                    component.package_l_mm = package_l_mm
                    updated = True
                
                if package_w_mm and not component.package_w_mm:
                    component.package_w_mm = package_w_mm
                    updated = True
                
                if package_h_mm and not component.package_h_mm:
                    component.package_h_mm = package_h_mm
                    updated = True
                
                # Update extras
                if 'extras' in row:
                    if not component.extras:
                        component.extras = row['extras']
                        updated = True
                    else:
                        # Merge extras
                        for key, value in row['extras'].items():
                            if key not in component.extras or not component.extras[key]:
                                component.extras[key] = value
                                updated = True
                
                if updated and not self.dry_run:
                    component.save()
                    self.results['updated'] += 1
                else:
                    self.results['skipped'] += 1
            
            else:
                # Create new component
                component_data = {
                    'mpn': mpn,
                    'mpn_norm': mpn_norm,
                    'manufacturer': manufacturer,
                    'manufacturer_norm': manufacturer_norm,
                    'value': row.get('value'),
                    'tolerance': row.get('tolerance'),
                    'wattage': row.get('wattage'),
                    'voltage': row.get('voltage'),
                    'current': row.get('current'),
                    'package_name': package_name,
                    'package_l_mm': package_l_mm,
                    'package_w_mm': package_w_mm,
                    'package_h_mm': package_h_mm,
                    'description': row.get('description'),
                    'url_datasheet': row.get('url_datasheet'),
                    'category_l1': category_l1,
                    'category_l2': category_l2,
                    # DMT Classification
                    'dmtuid': row.get('dmtuid'),
                    'dmt_tt': row.get('dmt_tt'),
                    'dmt_ff': row.get('dmt_ff'),
                    'dmt_cc': row.get('dmt_cc'),
                    'dmt_ss': row.get('dmt_ss'),
                    'dmt_xxx': row.get('dmt_xxx'),
                }

                if 'extras' in row:
                    component_data['extras'] = row['extras']

                if not self.dry_run:
                    component = Component.objects.create(**component_data)
                    self.results['created'] += 1
                else:
                    self.results['created'] += 1
            
            # Create inventory item if quantity is provided
            if not self.dry_run and component and 'quantity' in row and row['quantity']:
                try:
                    quantity = int(row['quantity'])
                    if quantity > 0:
                        InventoryItem.objects.create(
                            component=component,
                            quantity=quantity,
                            uom=row.get('uom', 'pcs'),
                            storage_location=row.get('storage_location', 'Unspecified'),
                            condition=row.get('condition', 'new')
                        )
                except (ValueError, TypeError):
                    pass
        
        except Exception as e:
            self.results['errors'] += 1
            self.results['error_rows'].append({
                'row': row,
                'error': str(e)
            })
    
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