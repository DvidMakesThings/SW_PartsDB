"""
Admin configuration for inventory models.
"""
from django.contrib import admin
from django.db.models import Count

from .models import Component, InventoryItem


class InventoryItemInline(admin.TabularInline):
    model = InventoryItem
    extra = 0
    fields = ('quantity', 'uom', 'storage_location', 'condition', 'supplier')


@admin.register(Component)
class ComponentAdmin(admin.ModelAdmin):
    list_display = ('mpn', 'manufacturer', 'value', 'package_name', 'category_l1', 'category_l2', 'in_stock')
    list_filter = ('manufacturer', 'category_l1', 'lifecycle', 'package_name')
    search_fields = ('mpn', 'manufacturer', 'description')
    readonly_fields = ('created_at', 'updated_at')
    inlines = [InventoryItemInline]
    fieldsets = (
        ('Basic Information', {
            'fields': ('mpn', 'manufacturer', 'description', 'value')
        }),
        ('Electrical Characteristics', {
            'fields': ('tolerance', 'wattage', 'voltage', 'current'),
        }),
        ('Package Information', {
            'fields': ('package_name', 'package_l_mm', 'package_w_mm', 
                       'package_h_mm', 'pins', 'pitch_mm')
        }),
        ('Categorization', {
            'fields': ('category_l1', 'category_l2', 'lifecycle', 'rohs', 'temp_grade')
        }),
        ('Documentation', {
            'fields': ('url_datasheet', 'url_alt')
        }),
        ('Integration', {
            'fields': ('footprint_name', 'step_model_path')
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at', 'extras'),
            'classes': ('collapse',)
        }),
    )

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        queryset = queryset.annotate(
            inventory_count=Count('inventory_items')
        )
        return queryset

    def in_stock(self, obj):
        return obj.inventory_count > 0
    in_stock.boolean = True
    in_stock.admin_order_field = 'inventory_count'
    
    actions = ['fetch_datasheets']
    
    def fetch_datasheets(self, request, queryset):
        count = 0
        for component in queryset:
            if component.url_datasheet:
                # In real implementation, this would call the Celery task
                # Will be implemented when we create the task
                count += 1
        
        self.message_user(
            request, 
            f"{count} datasheets queued for download."
        )
    fetch_datasheets.short_description = "Fetch datasheet for selected components"


@admin.register(InventoryItem)
class InventoryItemAdmin(admin.ModelAdmin):
    list_display = ('component', 'quantity', 'uom', 'storage_location', 'condition')
    list_filter = ('condition', 'uom')
    search_fields = ('component__mpn', 'component__manufacturer', 'storage_location')
    autocomplete_fields = ['component']
    readonly_fields = ('created_at', 'updated_at')