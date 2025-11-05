"""
Celery tasks for the files app.
"""
import os
import hashlib
from pathlib import Path
import logging
import requests
from django.conf import settings
from django.core.files.base import ContentFile
from celery import shared_task
from .models import Attachment
from .services import datasheet_relpath
from apps.inventory.models import Component

logger = logging.getLogger(__name__)


def download_datasheet(url):
    """
    Download a datasheet from a URL
    """
    headers = {
        'User-Agent': 'PartsDB/1.0 (https://github.com/DvidMakesThings/SW_PartsDB)'
    }
    response = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
    response.raise_for_status()
    
    # Verify it's a PDF by checking the content type and first bytes
    content_type = response.headers.get('Content-Type', '')
    if not content_type.lower() == 'application/pdf' and not content_type.lower() == 'application/octet-stream':
        # Additional check for PDF magic number
        if not response.content.startswith(b'%PDF'):
            raise ValueError(f"Downloaded file is not a PDF (content-type: {content_type})")
    
    return response.content


def save_datasheet(component, file_content):
    """
    Save a datasheet to the media directory and create an Attachment
    Stores in {MPN}/{MPN}.pdf format
    """
    if not component.mpn:
        raise ValueError("Component must have an MPN to save datasheet")

    # Calculate SHA256
    sha256 = hashlib.sha256(file_content).hexdigest()

    # Check if this component already has a datasheet attachment
    existing = Attachment.objects.filter(component=component, type='datasheet').first()
    if existing:
        # Update existing attachment
        existing.sha256 = sha256
        existing.source_url = component.url_datasheet

        # Sanitize MPN for path
        safe_mpn = "".join(c for c in component.mpn if c.isalnum() or c in ('-', '_', '.'))
        if not safe_mpn:
            safe_mpn = f"component_{component.id}"
        filename = f"{safe_mpn}.pdf"

        # Save the file
        existing.file.save(filename, ContentFile(file_content), save=True)
        return existing.file.path

    # Create a new attachment
    attachment = Attachment(
        component=component,
        type='datasheet',
        source_url=component.url_datasheet,
        sha256=sha256
    )

    # Sanitize MPN for path
    safe_mpn = "".join(c for c in component.mpn if c.isalnum() or c in ('-', '_', '.'))
    if not safe_mpn:
        safe_mpn = f"component_{component.id}"
    filename = f"{safe_mpn}.pdf"

    # Save the file (upload_to will handle the folder structure)
    attachment.file.save(filename, ContentFile(file_content), save=True)

    return attachment.file.path


@shared_task(bind=True)
def fetch_datasheet(self, component_id):
    """
    Fetch a datasheet and save it to the media directory
    """
    try:
        component = Component.objects.get(id=component_id)
        if not component.url_datasheet:
            return {"error": "No datasheet URL specified"}
        
        # Download the file
        file_content = download_datasheet(component.url_datasheet)
        
        # Save the file
        file_path = save_datasheet(component, file_content)
        
        return {"saved": True, "path": file_path}
    
    except Component.DoesNotExist:
        logger.error(f"Component with ID {component_id} does not exist")
        return {"error": "Component not found"}
    
    except requests.RequestException as e:
        logger.error(f"Failed to download datasheet for component {component_id}: {e}")
        return {"error": f"Download failed: {str(e)}"}
    
    except ValueError as e:
        logger.error(f"Invalid datasheet for component {component_id}: {e}")
        return {"error": str(e)}
    
    except Exception as e:
        logger.error(f"Unexpected error processing datasheet for component {component_id}: {e}")
        return {"error": f"Processing error: {str(e)}"}