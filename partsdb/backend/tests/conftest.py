import shutil
import pytest
from django.conf import settings
from rest_framework.test import APIClient


@pytest.fixture(autouse=True, scope="session")
def _temp_media(tmp_path_factory):
    """Override MEDIA_ROOT to use a temporary directory for tests."""
    p = tmp_path_factory.mktemp("media")
    settings.MEDIA_ROOT = str(p)
    yield
    shutil.rmtree(p, ignore_errors=True)


@pytest.fixture
def client():
    """Return a Django test client."""
    return APIClient()