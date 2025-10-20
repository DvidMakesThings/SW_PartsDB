from unittest.mock import patch, Mock
import os

import pytest
from django.urls import reverse

from apps.files.models import Attachment
from tests.factories import ComponentFactory

# Sample PDF content for testing
PDF = b"%PDF-1.7\n%Sample content for testing"
HTML = b"<html><body>Not a PDF</body></html>"


@pytest.mark.django_db
@patch("requests.get")
def test_fetch_pdf_saves_attachment(mock_get, client):
    """Test that fetching a valid PDF saves an attachment."""
    # Set up mock response for a valid PDF
    resp = Mock()
    resp.status_code = 200
    resp.headers = {"Content-Type": "application/pdf"}
    resp.iter_content = lambda chunk_size: [PDF]
    resp.content = PDF
    mock_get.return_value = resp
    
    # Create a component with a URL datasheet
    component = ComponentFactory(
        url_datasheet="https://example.com/datasheet.pdf",
        manufacturer="TEST",
        mpn="TEST123",
        category_l1="Interface"
    )
    
    # Call the fetch datasheet endpoint
    url = reverse("component-fetch-datasheet", kwargs={"pk": component.id})
    response = client.post(url)
    
    # Check the response
    assert response.status_code == 200
    assert response.json()["saved"] is True
    assert "path" in response.json()
    
    # Check that an attachment was created
    attachment = Attachment.objects.filter(component=component).first()
    assert attachment is not None
    assert attachment.type == "datasheet"
    assert attachment.sha256 is not None
    
    # Check that the file was saved to disk
    assert os.path.exists(os.path.join(attachment.file.path))


@pytest.mark.django_db
@patch("requests.get")
def test_fetch_pdf_dedupes(mock_get, client):
    """Test that fetching the same PDF twice doesn't create duplicate attachments."""
    # Set up mock response for a valid PDF
    resp = Mock()
    resp.status_code = 200
    resp.headers = {"Content-Type": "application/pdf"}
    resp.iter_content = lambda chunk_size: [PDF]
    resp.content = PDF
    mock_get.return_value = resp
    
    # Create a component with a URL datasheet
    component = ComponentFactory(
        url_datasheet="https://example.com/datasheet.pdf",
        manufacturer="TEST",
        mpn="DEDUPE",
        category_l1="Interface"
    )
    
    # Call the fetch datasheet endpoint twice
    url = reverse("component-fetch-datasheet", kwargs={"pk": component.id})
    response1 = client.post(url)
    assert response1.status_code == 200
    
    # Count attachments after first fetch
    attachment_count_1 = Attachment.objects.filter(component=component).count()
    assert attachment_count_1 == 1
    
    # Fetch again
    response2 = client.post(url)
    assert response2.status_code == 200
    
    # Count should still be 1
    attachment_count_2 = Attachment.objects.filter(component=component).count()
    assert attachment_count_2 == 1


@pytest.mark.django_db
@patch("requests.get")
def test_fetch_non_pdf_fails(mock_get, client):
    """Test that fetching a non-PDF file returns an error."""
    # Set up mock response for HTML content
    resp = Mock()
    resp.status_code = 200
    resp.headers = {"Content-Type": "text/html"}
    resp.content = HTML
    mock_get.return_value = resp
    
    # Create a component with a URL datasheet
    component = ComponentFactory(
        url_datasheet="https://example.com/not-a-pdf.html",
        manufacturer="TEST",
        mpn="HTML",
        category_l1="Interface"
    )
    
    # Call the fetch datasheet endpoint
    url = reverse("component-fetch-datasheet", kwargs={"pk": component.id})
    response = client.post(url)
    
    # Check the response is an error
    assert response.status_code in [400, 500]  # Accept either 400 or 500 as valid error responses
    assert "error" in response.json()
    
    # Check that no attachment was created
    attachment_count = Attachment.objects.filter(component=component).count()
    assert attachment_count == 0


@pytest.mark.django_db
@patch("requests.get")
def test_batch_fetch_datasheets(mock_get, client):
    """Test the batch datasheet fetching endpoint."""
    # Set up mock response for a valid PDF
    resp = Mock()
    resp.status_code = 200
    resp.headers = {"Content-Type": "application/pdf"}
    resp.iter_content = lambda chunk_size: [PDF]
    resp.content = PDF
    mock_get.return_value = resp
    
    # Create components with URL datasheets but no attachments
    components = [
        ComponentFactory(url_datasheet="https://example.com/datasheet1.pdf", manufacturer="TEST", mpn=f"BATCH{i}")
        for i in range(3)
    ]
    
    # Call the batch fetch endpoint
    url = reverse("component-fetch-missing-datasheets")
    response = client.post(url)
    
    # Check the response
    assert response.status_code == 200
    assert response.json()["count"] > 0
    
    # Check that attachments were created for all components
    for component in components:
        attachment = Attachment.objects.filter(component=component).first()
        assert attachment is not None