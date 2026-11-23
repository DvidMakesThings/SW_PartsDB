"""DMT hardware identifiers, including existing documents without a board segment."""
import re


def pbom_document_id(value):
    """Normalize only the document type; retain the project, board and revision."""
    value = str(value or "").strip().upper()
    match = re.fullmatch(r"DMT-HW-([A-Z0-9]{4,6})-(?:(\d{2})-)?(SCH|PCB|PBOM)-(V\d{3})", value)
    if not match or match[2] == "00":
        raise ValueError("Enter DOCUMENT_ID as DMT-HW-USBSW-01-SCH-V100 or "
                         "DMT-HW-VCTR-SCH-V100. PCB and PBOM types are also accepted.")
    project, board, _, revision = match.groups()
    normalized = f"DMT-HW-{project}-" + (f"{board}-" if board else "") + f"PBOM-{revision}"
    return normalized, project
