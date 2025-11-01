import pytest

def test_health_ok(client):
    """Test that the health check endpoint returns OK."""
    response = client.get("/api/health/")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_openapi_ok(client):
    """Test that the OpenAPI schema endpoint returns a valid schema."""
    response = client.get("/api/schema/")
    assert response.status_code == 200
    assert "openapi" in response.content.decode()
