"""
Views for the files app.
"""
from rest_framework import viewsets, filters
from rest_framework.parsers import MultiPartParser, FormParser
from django_filters.rest_framework import DjangoFilterBackend

from .models import Attachment
from .serializers import AttachmentSerializer


class AttachmentViewSet(viewsets.ModelViewSet):
    """
    API endpoint for attachments
    """
    queryset = Attachment.objects.all()
    serializer_class = AttachmentSerializer
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter
    ]
    filterset_fields = ['component', 'type']
    search_fields = ['component__mpn', 'component__manufacturer']
    ordering_fields = ['created_at', 'updated_at']
    ordering = ['-created_at']
    parser_classes = [MultiPartParser, FormParser]