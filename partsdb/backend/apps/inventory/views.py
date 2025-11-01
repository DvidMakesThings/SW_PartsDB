"""
Views for the inventory app.
"""
import csv
from django.db.models import Q, Count
from django.http import HttpResponse
from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend

from .models import Component, InventoryItem
from .serializers import ComponentSerializer, InventoryItemSerializer
from apps.files.tasks import fetch_datasheet


class ComponentViewSet(viewsets.ModelViewSet):
    """
    API endpoint for components
    """
    queryset = Component.objects.all()
    serializer_class = ComponentSerializer
    filter_backends = [
        DjangoFilterBackend, 
        filters.SearchFilter,
        filters.OrderingFilter
    ]
    filterset_fields = ['manufacturer', 'category_l1', 'package_name']
    search_fields = ['mpn', 'manufacturer', 'description', 'dmtuid', 'value', 'package_name']
    ordering_fields = ['mpn', 'manufacturer', 'created_at', 'updated_at']
    ordering = ['-created_at']
    
    def get_queryset(self):
        """
        Filter by in_stock_only if requested
        """
        queryset = super().get_queryset()
        queryset = queryset.annotate(inventory_count=Count('inventory_items'))

        # Filter by in_stock_only if param is provided
        in_stock_only = self.request.query_params.get('in_stock_only', False)
        if in_stock_only and in_stock_only.lower() in ('true', '1', 'yes'):
            queryset = queryset.filter(inventory_items__quantity__gt=0).distinct()

        # Filter by has_stock (same as in_stock_only)
        has_stock = self.request.query_params.get('has_stock', False)
        if has_stock and has_stock.lower() in ('true', '1', 'yes'):
            queryset = queryset.filter(inventory_items__quantity__gt=0).distinct()

        return queryset

    @action(detail=True, methods=['post'])
    def fetch_datasheet(self, request, pk=None):
        """
        Fetch datasheet for a component
        """
        component = self.get_object()
        if not component.url_datasheet:
            return Response(
                {"error": "No datasheet URL specified for this component"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Always run synchronously for testing
        try:
            # Try calling directly without Celery
            from apps.files.tasks import download_datasheet, save_datasheet
            file_content = download_datasheet(component.url_datasheet)
            file_path = save_datasheet(component, file_content)
            return Response({
                "saved": True, 
                "path": file_path,
                "message": "Datasheet downloaded successfully"
            })
        except Exception as e:
            return Response({
                "error": str(e),
                "message": "Failed to download datasheet"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['post'])
    def fetch_missing_datasheets(self, request):
        """
        Fetch datasheets for all components with url_datasheet but no file
        """
        # Find components with datasheet URL but no attachment
        components = Component.objects.filter(
            url_datasheet__isnull=False,
        ).exclude(
            attachments__type='datasheet'
        )
        
        count = components.count()
        
        # Run synchronously - but limit to avoid timeouts
        max_sync = 5
        results = []
        from apps.files.tasks import download_datasheet, save_datasheet
        
        for component in components[:max_sync]:
            try:
                file_content = download_datasheet(component.url_datasheet)
                file_path = save_datasheet(component, file_content)
                results.append({
                    "component_id": component.id,
                    "saved": True,
                    "path": file_path
                })
            except Exception as e:
                results.append({
                    "component_id": component.id,
                    "error": str(e)
                })
        
        return Response({
            "message": f"Downloaded {len(results)} datasheets (limited to {max_sync} for synchronous execution)",
            "count": len(results),
            "results": results
        })
    
    @action(detail=False, methods=['post'])
    def check_stock(self, request):
        """
        Check stock for a list of components
        """
        items = request.data
        if not isinstance(items, list):
            return Response(
                {"error": "Expected a list of items"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        results = []
        for item in items:
            manufacturer = item.get('manufacturer')
            mpn = item.get('mpn')
            quantity_needed = item.get('quantity_needed', 1)
            
            # Find the component
            try:
                component = Component.objects.get(
                    manufacturer__iexact=manufacturer,
                    mpn__iexact=mpn
                )
                total_quantity = sum(
                    inv.quantity for inv in component.inventory_items.all()
                )
                results.append({
                    'mpn': mpn,
                    'have': total_quantity,
                    'need': quantity_needed,
                    'ok': total_quantity >= quantity_needed
                })
            except Component.DoesNotExist:
                results.append({
                    'mpn': mpn,
                    'have': 0,
                    'need': quantity_needed,
                    'ok': False
                })
        
        return Response(results)

    @action(detail=False, methods=['get'])
    def export_csv(self, request):
        """
        Export all components to CSV format
        """
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="components_export.csv"'

        writer = csv.writer(response)

        # Write header row with all fields
        header = [
            'MPN', 'Manufacturer', 'Value', 'Tolerance', 'Package', 'Description',
            'Datasheet URL', 'Category L1', 'Category L2', 'DMTUID',
            'Domain (TT)', 'Family (FF)', 'Class (CC)', 'Style (SS)', 'Sequence (XXX)',
            'RoHS', 'Lifecycle', 'Operating Temperature'
        ]

        # Get all possible extras keys from the first few components
        components_sample = Component.objects.exclude(extras__isnull=True)[:100]
        extras_keys = set()
        for comp in components_sample:
            if comp.extras:
                extras_keys.update(comp.extras.keys())

        # Add extras keys to header
        header.extend(sorted(extras_keys))
        writer.writerow(header)

        # Write component data
        for component in Component.objects.all().iterator():
            row = [
                component.mpn,
                component.manufacturer,
                component.value or '',
                component.tolerance or '',
                component.package_name or '',
                component.description or '',
                component.url_datasheet or '',
                component.category_l1 or '',
                component.category_l2 or '',
                component.dmtuid or '',
                component.dmt_tt or '',
                component.dmt_ff or '',
                component.dmt_cc or '',
                component.dmt_ss or '',
                component.dmt_xxx or '',
                'YES' if component.rohs else 'NO' if component.rohs is False else '',
                component.lifecycle or '',
                component.temp_grade or '',
            ]

            # Add extras data
            for key in sorted(extras_keys):
                row.append(component.extras.get(key, '') if component.extras else '')

            writer.writerow(row)

        return response


class InventoryItemViewSet(viewsets.ModelViewSet):
    """
    API endpoint for inventory items
    """
    queryset = InventoryItem.objects.all()
    serializer_class = InventoryItemSerializer
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter
    ]
    filterset_fields = ['component', 'uom', 'condition', 'storage_location']
    search_fields = ['component__mpn', 'component__manufacturer', 'storage_location']
    ordering_fields = ['created_at', 'updated_at']
    ordering = ['-created_at']

    @action(detail=False, methods=['get'])
    def by_location(self, request):
        """
        Group inventory items by storage location
        """
        from django.db.models import Sum

        locations = {}

        # Get all inventory items grouped by location
        items = InventoryItem.objects.select_related('component').all()

        for item in items:
            location = item.storage_location
            if location not in locations:
                locations[location] = {
                    'location': location,
                    'total_items': 0,
                    'total_components': 0,
                    'components': []
                }

            locations[location]['total_items'] += item.quantity
            locations[location]['total_components'] += 1
            locations[location]['components'].append({
                'id': str(item.component.id),
                'mpn': item.component.mpn,
                'manufacturer': item.component.manufacturer,
                'description': item.component.description or '',
                'quantity': item.quantity,
                'uom': item.uom,
            })

        # Sort locations by name
        result = sorted(locations.values(), key=lambda x: x['location'])

        return Response(result)