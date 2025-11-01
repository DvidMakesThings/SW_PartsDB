"""
CSV importer for the inventory app.
"""
import os
import csv
import re
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
        Clean text by fixing encoding issues and normalizing characters
        """
        if not value:
            return value
        # Fix common encoding issues
        value = value.replace('\u00c2\u00b0', '\u00b0')  # Fix Â° to °
        value = value.replace('Â°', '°')  # Another variant
        value = value.replace('\u00c2', '')  # Remove stray Â
        # Replace Unicode dashes with ASCII hyphen
        value = re.sub(r'[\u2010-\u2015]', '-', value)
        return value.strip()

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
        Read the CSV file and yield rows as dictionaries
        """
        with open(self.file_path, 'r', encoding=self.encoding) as csvfile:
            reader = csv.DictReader(csvfile, delimiter=self.delimiter)
            
            # Map CSV headers to model fields
            header_map = {}
            for model_field, csv_headers in self.field_map.items():
                for header in reader.fieldnames:
                    if header.lower() in [h.lower() for h in csv_headers]:
                        header_map[header] = model_field
            
            # Process each row
            for row in reader:
                mapped_row = {}
                extras = {}
                
                # Map fields using the header map
                for header, value in row.items():
                    if header in header_map:
                        model_field = header_map[header]
                        mapped_row[model_field] = self.clean_text(value)
                    else:
                        # Store unknown fields in extras
                        extras[header.lower()] = self.clean_text(value)
                
                if extras:
                    mapped_row['extras'] = extras
                
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