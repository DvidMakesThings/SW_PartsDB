"""
Admin configuration for files models.
"""
from django.contrib import admin

from .models import Attachment


@admin.register(Attachment)
class AttachmentAdmin(admin.ModelAdmin):
    list_display = ('component', 'type', 'file', 'sha256')
    list_filter = ('type',)
    search_fields = ('component__mpn', 'component__manufacturer', 'sha256')
    autocomplete_fields = ['component']