"""
Views for the files app.
"""
import logging
from rest_framework import viewsets, filters, status
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from django_filters.rest_framework import DjangoFilterBackend

from .models import Attachment
from .serializers import AttachmentSerializer

logger = logging.getLogger(__name__)


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

    def create(self, request, *args, **kwargs):
        """Override create to add logging"""
        logger.info(f"File upload request received: {request.data}")
        logger.info(f"Files: {request.FILES}")

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)

        logger.info(f"File uploaded successfully: {serializer.data}")

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)