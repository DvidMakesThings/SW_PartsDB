"""
Serializers for the files app.
"""
from rest_framework import serializers
from .models import Attachment


class AttachmentSerializer(serializers.ModelSerializer):
    """Serializer for file attachments"""
    
    class Meta:
        model = Attachment
        fields = '__all__'