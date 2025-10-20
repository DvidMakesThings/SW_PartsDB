from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import health

router = DefaultRouter()

urlpatterns = [
    path('health/', health, name='health-check'),
    path('', include(router.urls)),
]