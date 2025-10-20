"""
Admin configuration for eagle models.
"""
from django.contrib import admin

from .models import EagleLink


@admin.register(EagleLink)
class EagleLinkAdmin(admin.ModelAdmin):
    list_display = ('component', 'eagle_library', 'eagle_device', 'eagle_package')
    search_fields = ('component__mpn', 'component__manufacturer', 'eagle_library', 'eagle_device')
    autocomplete_fields = ['component']