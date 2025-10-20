"""
Models for the files app.
"""
from django.db import models

from apps.core.models import TimeStampedModel
from apps.inventory.models import Component


class Attachment(TimeStampedModel):
    """
    Model representing a file attachment for a component.
    """
    TYPE_CHOICES = (
        ('datasheet', 'Datasheet'),
        ('three_d', '3D Model'),
        ('photo', 'Photo'),
        ('appnote', 'Application Note'),
        ('other', 'Other'),
    )
    
    component = models.ForeignKey(
        Component, 
        on_delete=models.CASCADE,
        related_name='attachments'
    )
    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    file = models.FileField(upload_to='uploads/')  # Will be overridden by service
    source_url = models.URLField(null=True, blank=True)
    sha256 = models.CharField(max_length=64, null=True, blank=True, db_index=True)
    
    class Meta:
        verbose_name = "Attachment"
        verbose_name_plural = "Attachments"
        indexes = [
            models.Index(fields=['type']),
            models.Index(fields=['sha256']),
        ]
    
    def __str__(self):
        return f"{self.component} - {self.get_type_display()}"