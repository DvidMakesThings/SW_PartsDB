from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import ComponentViewSet, InventoryItemViewSet
from .import_views import ImportCSVView

router = DefaultRouter()
router.register(r'components', ComponentViewSet)
router.register(r'inventory', InventoryItemViewSet)

urlpatterns = [
    path('import/csv/', ImportCSVView.as_view(), name='import-csv'),
    path('', include(router.urls)),
]