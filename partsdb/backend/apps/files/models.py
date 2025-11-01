"""
Models for the files app.
"""
from django.db import models

from apps.core.models import TimeStampedModel
from apps.inventory.models import Component


def attachment_upload_path(instance, filename):
    """
    Generate upload path for attachments.
    All files are stored in MPN-named folders: {MPN}/{filename}
    """
    mpn = instance.component.mpn
    # Sanitize MPN for use in path (remove invalid characters)
    safe_mpn = "".join(c for c in mpn if c.isalnum() or c in ('-', '_', '.'))
    return f"{safe_mpn}/{filename}"


class Attachment(TimeStampedModel):
    """
    Model representing a file attachment for a component.
    """
    TYPE_CHOICES = (
        ('datasheet', 'Datasheet'),
        ('three_d', '3D Model (STEP)'),
        ('eagle_lib', 'Eagle Library'),
        ('photo', 'Photo'),
        ('appnote', 'Application Note'),
        ('schematic', 'Schematic'),
        ('layout', 'Layout/PCB'),
        ('other', 'Other'),
    )

    component = models.ForeignKey(
        Component,
        on_delete=models.CASCADE,
        related_name='attachments'
    )
    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    custom_type = models.CharField(max_length=100, null=True, blank=True, help_text='Custom file type when "Other" is selected')
    file = models.FileField(upload_to=attachment_upload_path)
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