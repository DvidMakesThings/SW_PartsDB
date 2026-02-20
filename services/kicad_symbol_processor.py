"""
services.kicad_symbol_processor - Process KiCad symbol files.

Parses .kicad_sym files and fills in property values from Part data.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from db.models import Part


class KiCadSymbolProcessor:
    """Process and modify KiCad symbol (.kicad_sym) files."""

    # Property name mappings: symbol property -> Part attribute or callable
    PROPERTY_MAP = {
        "Value": "_get_value",
        "Footprint": "kicad_footprint",
        "Datasheet": "datasheet",
        "Description": "description",
        "MFR": "manufacturer",
        "MPN": "mpn",
        "ROHS": "_const_YES",
    }

    @classmethod
    def process_symbol(cls, content: str, part: Optional[Part] = None) -> str:
        """
        Process a KiCad symbol file content and fill in properties from Part data.
        
        Args:
            content: The raw .kicad_sym file content
            part: Optional Part object to pull data from
            
        Returns:
            Modified symbol content with filled properties
        """
        if not part:
            return content

        for prop_name, source in cls.PROPERTY_MAP.items():
            value = cls._get_property_value(part, source)
            if value:
                content = cls._set_property(content, prop_name, value)

        return content

    @classmethod
    def _get_property_value(cls, part: Part, source: str) -> str:
        """Get a property value from the Part object."""
        if source.startswith("_"):
            # Call a method
            method = getattr(cls, source, None)
            if method:
                return method(part)
            return ""
        else:
            # Direct attribute
            return getattr(part, source, "") or ""

    @classmethod
    def _get_value(cls, part: Part) -> str:
        """
        Generate the Value property.
        For passives: value field (e.g., "100nF 50V", "10R 1%")
        For others: MPN
        """
        # If there's a value field, use it (passives)
        if part.value and part.value.strip():
            return part.value
        # Otherwise use MPN
        if part.mpn and part.mpn.strip():
            return part.mpn
        return ""

    @classmethod
    def _const_YES(cls, part: Part) -> str:
        """Return constant YES for RoHS."""
        return "YES"

    @classmethod
    def _set_property(cls, content: str, prop_name: str, value: str) -> str:
        """
        Set a property value in the symbol content.
        
        Handles the KiCad S-expression format:
        (property "Name" "value" ...)
        """
        # Escape special characters for the replacement value
        escaped_value = value.replace("\\", "\\\\").replace('"', '\\"')
        
        # Pattern to find the property and replace its value
        # Matches: (property "PropName" "old_value"
        pattern = rf'(\(property\s+"{re.escape(prop_name)}"\s+)"[^"]*"'
        replacement = rf'\1"{escaped_value}"'
        
        new_content, count = re.subn(pattern, replacement, content)
        
        return new_content

    @classmethod
    def extract_properties(cls, content: str) -> dict:
        """
        Extract all properties from a symbol file.
        
        Returns:
            Dict of property_name -> value
        """
        props = {}
        # Match (property "Name" "Value" ...)
        pattern = r'\(property\s+"([^"]+)"\s+"([^"]*)"'
        for match in re.finditer(pattern, content):
            props[match.group(1)] = match.group(2)
        return props

    @classmethod
    def get_symbol_name(cls, content: str) -> Optional[str]:
        """Extract the symbol name from the file content."""
        # Match (symbol "LibName:SymbolName" or just (symbol "SymbolName"
        match = re.search(r'\(symbol\s+"([^"]+)"', content)
        if match:
            name = match.group(1)
            # Strip library prefix if present
            if ":" in name:
                name = name.split(":", 1)[1]
            return name

    @classmethod
    def set_symbol_name(cls, content: str, new_name: str) -> str:
        """
        Set the symbol name in the file content.
        
        Updates both the main symbol declaration and any nested symbol references.
        """
        # Escape special characters
        escaped_name = new_name.replace("\\", "\\\\").replace('"', '\\"')
        
        # Replace the main symbol name (first occurrence after kicad_symbol_lib)
        # Match: (symbol "old_name" with optional library prefix
        pattern = r'(\(symbol\s+)"[^"]*"'
        
        def replace_first(match):
            return f'{match.group(1)}"{escaped_name}"'
        
        # Only replace the first occurrence (main symbol declaration)
        new_content = re.sub(pattern, replace_first, content, count=1)
        
        return new_content
        return None


def process_uploaded_symbol(filepath: Path, part: Optional[Part] = None) -> dict:
    """
    Process an uploaded symbol file.
    
    Args:
        filepath: Path to the .kicad_sym file
        part: Optional Part to fill properties from
        
    Returns:
        Dict with processing results
    """
    content = filepath.read_text(encoding="utf-8")
    
    # Extract original properties
    original_props = KiCadSymbolProcessor.extract_properties(content)
    
    # Process and fill properties
    if part:
        new_content = KiCadSymbolProcessor.process_symbol(content, part)
        filepath.write_text(new_content, encoding="utf-8")
        new_props = KiCadSymbolProcessor.extract_properties(new_content)
    else:
        new_props = original_props
    
    return {
        "symbol_name": KiCadSymbolProcessor.get_symbol_name(content),
        "original_properties": original_props,
        "updated_properties": new_props,
        "part_linked": part.dmtuid if part else None,
    }
