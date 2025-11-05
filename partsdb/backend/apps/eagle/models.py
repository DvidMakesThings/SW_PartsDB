"""
Models for the Eagle integration app.
"""
from django.db import models

from apps.core.models import TimeStampedModel
from apps.inventory.models import Component


class EagleLink(TimeStampedModel):
    """
    Model representing a link between a component and an Eagle library.
    """
    component = models.ForeignKey(
        Component, 
        on_delete=models.CASCADE,
        related_name='eagle_links'
    )
    eagle_library = models.CharField(max_length=255)
    eagle_device = models.CharField(max_length=255)
    eagle_package = models.CharField(max_length=255)
    notes = models.TextField(null=True, blank=True)
    
    class Meta:
        verbose_name = "Eagle Link"
        verbose_name_plural = "Eagle Links"
        unique_together = ('component', 'eagle_library', 'eagle_device')
    
    def __str__(self):
        return f"{self.component} - {self.eagle_library}.{self.eagle_device}"