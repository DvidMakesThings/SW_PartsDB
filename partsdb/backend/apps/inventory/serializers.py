"""
Serializers for the inventory app.
"""
from rest_framework import serializers
from .models import Component, InventoryItem


class InventoryItemSerializer(serializers.ModelSerializer):
    """Serializer for inventory items"""

    class Meta:
        model = InventoryItem
        fields = '__all__'


class AttachmentSimpleSerializer(serializers.Serializer):
    """Simple serializer for attachments to avoid circular imports"""
    id = serializers.IntegerField()
    type = serializers.CharField()
    custom_type = serializers.CharField(required=False, allow_null=True)
    file = serializers.CharField()
    file_url = serializers.SerializerMethodField()
    source_url = serializers.CharField(required=False, allow_null=True)
    created_at = serializers.DateTimeField()

    def get_file_url(self, obj):
        """Return the full URL for the file"""
        if hasattr(obj, 'file') and obj.file:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.file.url)
            return obj.file.url
        return None


class ComponentSerializer(serializers.ModelSerializer):
    """Serializer for components"""
    inventory_items = InventoryItemSerializer(many=True, read_only=True)
    attachments = AttachmentSimpleSerializer(many=True, read_only=True)

    class Meta:
        model = Component
        fields = '__all__'