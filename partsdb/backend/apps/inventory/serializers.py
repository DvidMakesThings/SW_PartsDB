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


class ComponentSerializer(serializers.ModelSerializer):
    """Serializer for components"""
    inventory_items = InventoryItemSerializer(many=True, read_only=True)
    
    class Meta:
        model = Component
        fields = '__all__'