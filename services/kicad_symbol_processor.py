"""
services.kicad_symbol_processor - Process KiCad symbol files.

Parses .kicad_sym files and fills in property values from Part data.
Manages consolidated DMTDB.kicad_sym library.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from kiutils.symbol import SymbolLib, Symbol

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
        
        Updates both the main symbol declaration and nested symbol units.
        Nested symbols follow pattern: ParentName_0_1, ParentName_1_1, etc.
        """
        # First, extract the old symbol name
        old_name = cls.get_symbol_name(content)
        
        # Escape special characters for new name
        escaped_name = new_name.replace("\\", "\\\\").replace('"', '\\"')
        
        # Replace the main symbol name (first occurrence)
        pattern = r'(\(symbol\s+)"[^"]*"'
        
        def replace_first(match):
            return f'{match.group(1)}"{escaped_name}"'
        
        new_content = re.sub(pattern, replace_first, content, count=1)
        
        # Now rename nested symbols (units like OldName_0_1, OldName_1_1, etc.)
        if old_name:
            # Pattern for nested symbol units: (symbol "OldName_N_N"
            # where N is a digit - e.g., "0402_0_1", "0402_1_1"
            nested_pattern = rf'(\(symbol\s+)"{re.escape(old_name)}_(\d+_\d+)"'
            nested_replacement = rf'\1"{escaped_name}_\2"'
            new_content = re.sub(nested_pattern, nested_replacement, new_content)
        
        return new_content

    @classmethod
    def extract_symbol_block(cls, content: str) -> Optional[str]:
        """
        Extract the (symbol ...) block from a .kicad_sym file.
        
        Removes the library wrapper, returning just the symbol definition.
        """
        # Find the first (symbol "..." that's the main symbol (not nested)
        # The main symbol is indented with one tab after the header
        match = re.search(r'(\t\(symbol\s+"[^"]+"\s*\n[\s\S]*?)(?=\n\)$|\Z)', content)
        if match:
            return match.group(1).rstrip()
        
        # Fallback: find any (symbol block
        match = re.search(r'(\(symbol\s+"[^"]+"\s*[\s\S]*?)(?=\n\)\s*$|\Z)', content)
        if match:
            block = match.group(1).rstrip()
            # Add proper indentation if missing
            if not block.startswith('\t'):
                block = '\t' + block.replace('\n', '\n\t').rstrip('\t')
            return block
        
        return None

    @staticmethod
    def _normalize_line_endings(content: str) -> str:
        """Normalize line endings to LF only (Unix-style)."""
        return content.replace('\r\n', '\n').replace('\r', '\n')

    @classmethod
    def add_symbol_to_library(cls, library_path: Path, symbol_content: str, symbol_name: str, skip_exists_check: bool = False) -> str:
        """
        Add or update a symbol in the consolidated library file using string manipulation.
        This preserves existing formatting (including 'hide yes' attributes).
        
        Args:
            library_path: Path to the .kicad_sym library file
            symbol_content: The (symbol ...) block to add (as string)
            symbol_name: Name of the symbol (for replacement detection)
            skip_exists_check: If True, skip duplicate check (not recommended)
            
        Returns:
            "added" if symbol was added
            "exists" if symbol already exists (skipped)
            "error" if failed
        """
        import re
        
        # Normalize line endings (only strip trailing whitespace, preserve leading tab)
        symbol_content = cls._normalize_line_endings(symbol_content.rstrip())
        
        # Ensure symbol starts with tab (KiCad format requires it)
        if not symbol_content.startswith('\t'):
            symbol_content = '\t' + symbol_content
        
        # The symbol_content from generate_passive_symbol uses tabs already
        
        if not library_path.exists():
            # Create new library file
            lib_content = f"""(kicad_symbol_lib
\t(version 20241209)
\t(generator "dmtdb")
\t(generator_version "1.0")
{symbol_content}
)
"""
            library_path.write_text(lib_content, encoding='utf-8')
            return "added"
        
        # Read existing library (try multiple encodings)
        lib_text = None
        encoding = 'utf-8'
        for enc in ['utf-8', 'latin-1', 'cp1252']:
            try:
                lib_text = library_path.read_text(encoding=enc)
                encoding = enc
                break
            except UnicodeDecodeError:
                continue
        
        if lib_text is None:
            print("Warning: Could not read library file")
            return "error"
        
        # Check if symbol already exists (by name)
        # Pattern matches (symbol "SymbolName" ...) accounting for possible whitespace
        escaped_name = re.escape(symbol_name)
        pattern = rf'\(symbol\s+"{escaped_name}"\s+'
        
        if re.search(pattern, lib_text):
            print(f"Note: Symbol '{symbol_name}' already exists in library")
            return "exists"
        
        # Also check if MPN already exists in library (to prevent duplicates with different names)
        mpn_match = re.search(r'\(property\s+"MPN"\s+"([^"]+)"', symbol_content)
        if mpn_match:
            mpn_value = mpn_match.group(1)
            if mpn_value:  # Don't check empty MPNs
                escaped_mpn = re.escape(mpn_value)
                mpn_pattern = rf'\(property\s+"MPN"\s+"{escaped_mpn}"'
                if re.search(mpn_pattern, lib_text):
                    print(f"Note: Symbol with MPN '{mpn_value}' already exists in library")
                    return "exists"
        
        # Insert new symbol before the final closing paren
        # Find the last ) in the file
        last_paren_idx = lib_text.rfind(')')
        if last_paren_idx == -1:
            print("Warning: Invalid library file format")
            return "error"
        
        # Convert tabs to 2 spaces to match library format (if library uses spaces)
        # Check what indentation the library uses
        if '\t(symbol ' not in lib_text and '  (symbol ' in lib_text:
            # Library uses spaces, convert tabs to spaces
            symbol_content = symbol_content.replace('\t', '  ')
        
        # Ensure proper formatting: newline before symbol if needed
        before_text = lib_text[:last_paren_idx].rstrip()
        new_lib_text = before_text + "\n" + symbol_content + "\n" + lib_text[last_paren_idx:]
        
        library_path.write_text(new_lib_text, encoding=encoding)
        return "added"

    @classmethod
    def list_symbols_in_library(cls, library_path: Path) -> list[str]:
        """List all symbol names in a library file using kiutils."""
        if not library_path.exists():
            return []
        
        try:
            lib = SymbolLib.from_file(library_path)
            return [sym.entryName for sym in lib.symbols]
        except Exception as e:
            print(f"Warning: Error reading library: {e}")
            return []

    @classmethod
    def _is_polarized_capacitor(cls, part) -> bool:
        """
        Detect if a capacitor is polarized based on part data.
        
        Returns True if polarized (requiring manual symbol upload).
        Returns False if non-polarized (safe for auto-generation).
        """
        # Primary detection: CC code for capacitors (TT=01, FF=01)
        # Polarized CC codes:
        #   02 = Aluminum Electrolytic
        #   03 = Tantalum
        #   04 = Polymer (Al or Ta)
        #   06 = Supercapacitor EDLC
        cc = getattr(part, 'cc', '') or ''
        if cc in ('02', '03', '04', '06'):
            return True
        
        # Check footprint name: "CP_" prefix indicates polarized
        fp = (getattr(part, 'kicad_footprint', '') or "").upper()
        if "CP_" in fp or "CP_ELEC" in fp:
            return True
        
        # Check Dielectric/Type field for polarized types
        dielectric = ""
        for field in getattr(part, 'fields', []):
            if field.field_name.lower() in ("dielectric", "type", "technology"):
                dielectric = (field.field_value or "").upper()
                break
        
        # Polarized dielectric types
        polarized_keywords = ["ALUMINUM", "TANTALUM", "POLYMER", "ELECTROLYTIC", "POLARIZED", "ELCO"]
        for kw in polarized_keywords:
            if kw in dielectric:
                return True
        
        # Check description for clues
        desc = (getattr(part, 'description', '') or "").upper()
        for kw in polarized_keywords:
            if kw in desc:
                return True
        
        # Default: assume non-polarized (MLCC is most common)
        return False

    @classmethod
    def generate_passive_symbol(cls, part: Part, library_path: Path) -> str:
        """
        Auto-generate a symbol for a passive component (R/C) from part data.
        
        Args:
            part: Part object with value, mpn, manufacturer, etc.
            library_path: Path to the target library file
            
        Returns:
            "added" if symbol was added
            "exists" if symbol already exists
            "error" if failed (e.g., polarized cap, inductor)
        """
        import re
        
        # Determine component type from family code
        # ff: "01" = Capacitor, "02" = Resistor, "03" = Inductor
        component_type = "resistor"  # default
        ref_des = "R"
        default_fp = "DMTDB:R_0402_1005Metric"
        
        if part.ff == "01":
            component_type = "capacitor"
            ref_des = "C"
            default_fp = "DMTDB:C_0402_1005Metric"
            
            # Check if capacitor is polarized - skip auto-generation if so
            if cls._is_polarized_capacitor(part):
                return "error"  # Requires manual symbol upload
                
        elif part.ff == "03":
            # Inductors vary too much - skip auto-generation
            return "error"
        
        # Generate symbol name: "Value MPN"
        value = part.value or ""
        mpn = part.mpn or ""
        mpn_sanitized = re.sub(r'[<>:"/\\|?*]', '_', mpn)
        
        if value and mpn_sanitized:
            symbol_name = f"{value} {mpn_sanitized}"
        elif mpn_sanitized:
            symbol_name = mpn_sanitized
        elif value:
            symbol_name = value
        else:
            return "error"  # Can't generate without name
        
        # Determine footprint short name (0402, 0603, etc.)
        fp = part.kicad_footprint or ""
        fp_short = ""
        # Check standard SMD sizes
        for size in ["0201", "0402", "0603", "0805", "1206", "1210", "2010", "2512"]:
            if size in fp:
                fp_short = size
                break
        # Check electrolytic cap sizes
        if not fp_short and "CP_Elec" in fp:
            # Extract size like "4x5.7" from "CP_Elec_4x5.7"
            match = re.search(r'CP_Elec_(\d+\.?\d*x\d+\.?\d*)', fp)
            if match:
                fp_short = match.group(1)
        
        # Generate symbol shape based on component type
        if component_type == "capacitor":
            # Capacitor: two parallel lines
            symbol_shape = f'''(symbol "{symbol_name}_0_1"
			(polyline
				(pts
					(xy -2.032 -0.762)
					(xy 2.032 -0.762)
				)
				(stroke
					(width 0.508)
					(type default)
				)
				(fill
					(type none)
				)
			)
			(polyline
				(pts
					(xy -2.032 0.762)
					(xy 2.032 0.762)
				)
				(stroke
					(width 0.508)
					(type default)
				)
				(fill
					(type none)
				)
			)
		)'''
            pin_positions = (3.81, -3.81)  # matching KiCad standard
            pin_length = 2.794
        else:
            # Resistor: rectangle
            symbol_shape = f'''(symbol "{symbol_name}_0_1"
			(rectangle
				(start -1.016 2.54)
				(end 1.016 -2.54)
				(stroke
					(width 0.254)
					(type default)
				)
				(fill
					(type none)
				)
			)
		)'''
            pin_positions = (3.81, -3.81)  # pins for resistor
            pin_length = 1.27  # connects exactly to rectangle body edge
        
        # Generate symbol content with proper template
        symbol_content = f'''	(symbol "{symbol_name}"
		(exclude_from_sim no)
		(in_bom yes)
		(on_board yes)
		(property "Reference" "{ref_des}"
			(at 2.032 2.032 0)
			(effects
				(font
					(size 1.27 1.27)
				)
				(justify left)
			)
		)
		(property "Value" "{value}"
			(at 2.032 0 0)
			(effects
				(font
					(size 1.27 1.27)
				)
				(justify left)
			)
		)
		(property "Footprint" "{part.kicad_footprint or default_fp}"
			(at 2.032 -4.064 0)
			(show_name)
			(effects
				(font
					(size 1.27 1.27)
				)
				(justify left)
				(hide yes)
			)
		)
		(property "Datasheet" "{part.datasheet or ''}"
			(at 2.032 -14.986 0)
			(show_name)
			(effects
				(font
					(size 1.27 1.27)
				)
				(justify left)
				(hide yes)
			)
		)
		(property "Description" "{(part.description or '').replace('"', "'")}"
			(at 2.032 -8.382 0)
			(show_name)
			(effects
				(font
					(size 1.27 1.27)
				)
				(justify left)
				(hide yes)
			)
		)
		(property "LCSC_PART" ""
			(at 2.032 -12.954 0)
			(show_name)
			(effects
				(font
					(size 1.27 1.27)
				)
				(justify left)
				(hide yes)
			)
		)
		(property "ROHS" "YES"
			(at 2.032 -6.35 0)
			(show_name)
			(effects
				(font
					(size 1.27 1.27)
				)
				(justify left)
				(hide yes)
			)
		)
		(property "FOOTPRINT_SHORT" "{fp_short}"
			(at 2.032 -2.032 0)
			(effects
				(font
					(size 1.27 1.27)
				)
				(justify left)
			)
		)
		(property "MFR" "{part.manufacturer or ''}"
			(at 2.032 -10.668 0)
			(show_name)
			(effects
				(font
					(size 1.27 1.27)
				)
				(justify left)
				(hide yes)
			)
		)
		(property "MPN" "{mpn}"
			(at 2.032 -17.018 0)
			(show_name)
			(effects
				(font
					(size 1.27 1.27)
				)
				(justify left)
				(hide yes)
			)
		)
		(property "DIST1" "{part.distributor or ''}"
			(at 2.286 -19.304 0)
			(show_name)
			(effects
				(font
					(size 1.27 1.27)
				)
				(justify left)
				(hide yes)
			)
		)
		{symbol_shape}
		(symbol "{symbol_name}_1_1"
			(pin passive line
				(at 0 {pin_positions[0]} 270)
				(length {pin_length})
				(name "~"
					(effects
						(font
							(size 1.27 1.27)
						)
					)
				)
				(number "1"
					(effects
						(font
							(size 1.27 1.27)
						)
					)
				)
			)
			(pin passive line
				(at 0 {pin_positions[1]} 90)
				(length {pin_length})
				(name "~"
					(effects
						(font
							(size 1.27 1.27)
						)
					)
				)
				(number "2"
					(effects
						(font
							(size 1.27 1.27)
						)
					)
				)
			)
		)
		(embedded_fonts no)
	)'''
        
        return cls.add_symbol_to_library(library_path, symbol_content, symbol_name)


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
