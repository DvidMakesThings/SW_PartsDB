"""
Serializers for the files app.
"""
import os
import hashlib
from pathlib import Path
from django.conf import settings
from rest_framework import serializers
from .models import Attachment
from .services import step_relpath


class AttachmentSerializer(serializers.ModelSerializer):
    """Serializer for file attachments"""
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = Attachment
        fields = ['id', 'component', 'type', 'custom_type', 'file', 'file_url', 'source_url', 'sha256', 'created_at', 'updated_at']

    def get_file_url(self, obj):
        """Return the full URL for the file"""
        if obj.file:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.file.url)
            return obj.file.url
        return None

    def create(self, validated_data):
        """
        Override create to handle file uploads with proper paths and deduplication
        """
        uploaded_file = validated_data.get('file')
        component = validated_data.get('component')
        file_type = validated_data.get('type')

        if uploaded_file:
            # Calculate SHA256 for deduplication
            file_content = uploaded_file.read()
            sha256 = hashlib.sha256(file_content).hexdigest()
            validated_data['sha256'] = sha256

            # Reset file pointer
            uploaded_file.seek(0)

            # Check if we already have this exact file
            existing = Attachment.objects.filter(sha256=sha256, type=file_type).first()
            if existing:
                # Reuse the existing file
                validated_data['file'] = existing.file
            else:
                # Determine the target path based on file type
                if file_type == 'three_d':
                    # Use component package info for 3D models
                    package = getattr(component, 'package', None) or 'Unknown'
                    variant = getattr(component, 'variant', None) or 'Generic'
                    mpn = component.mpn
                    rel_path = step_relpath(package, variant, mpn)

                    # Ensure directory exists
                    abs_dir = Path(settings.MEDIA_ROOT) / rel_path.parent
                    os.makedirs(abs_dir, exist_ok=True)

                    # Update the file name to include full relative path
                    uploaded_file.name = str(rel_path)

        return super().create(validated_data)