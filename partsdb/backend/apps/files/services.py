from pathlib import Path

def safe(s: str) -> str:
    """Make a string safe for use in filenames by replacing spaces and invalid characters."""
    return ''.join(c if c.isalnum() or c in '._- ' else '_' for c in s).replace(' ', '_')

def datasheet_relpath(manufacturer: str, cat_l1: str, mpn: str) -> Path:
    """Return a deterministic path for a datasheet file."""
    return Path("Datasheets") / safe(manufacturer) / safe(cat_l1 or "Unsorted") / (safe(mpn) + ".pdf")

def step_relpath(package: str, variant: str, mpn: str) -> Path:
    """Return a deterministic path for a 3D model file."""
    return Path("3D") / safe(package or "Unknown") / safe(variant or "Generic") / (safe(mpn) + ".step")

def photo_relpath(mpn: str) -> Path:
    """Return a deterministic path for a photo file."""
    return Path("Photos") / safe(mpn) / "front.jpg"