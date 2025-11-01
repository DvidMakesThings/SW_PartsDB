"""
Models for the inventory app.
"""
import re
from django.db import models
from django.utils.text import slugify

from apps.core.models import TimeStampedModel


class Component(TimeStampedModel):
    """
    Model representing an electronic component.
    """
    LIFECYCLE_CHOICES = (
        ('ACTIVE', 'Active'),
        ('NRND', 'Not Recommended for New Designs'),
        ('EOL', 'End of Life'),
        ('UNKNOWN', 'Unknown'),
    )

    # Basic identification
    mpn = models.CharField(
        max_length=255, 
        verbose_name="Manufacturer Part Number",
        help_text="Manufacturer's part number"
    )
    mpn_norm = models.CharField(
        max_length=255,
        verbose_name="Normalized MPN",
        help_text="Normalized MPN for consistent lookups",
        db_index=True,
        null=True,
        blank=True
    )
    manufacturer = models.CharField(max_length=255)
    manufacturer_norm = models.CharField(
        max_length=255,
        verbose_name="Normalized Manufacturer",
        help_text="Normalized manufacturer name for consistent lookups",
        db_index=True,
        null=True,
        blank=True
    )
    
    # Electrical characteristics
    value = models.CharField(max_length=100, null=True, blank=True)
    tolerance = models.CharField(max_length=50, null=True, blank=True)
    wattage = models.CharField(max_length=50, null=True, blank=True)
    voltage = models.CharField(max_length=50, null=True, blank=True)
    current = models.CharField(max_length=50, null=True, blank=True)
    
    # Package information
    package_name = models.CharField(max_length=100, null=True, blank=True)
    package_l_mm = models.DecimalField(
        max_digits=10, decimal_places=3, null=True, blank=True,
        verbose_name="Package Length (mm)"
    )
    package_w_mm = models.DecimalField(
        max_digits=10, decimal_places=3, null=True, blank=True,
        verbose_name="Package Width (mm)"
    )
    package_h_mm = models.DecimalField(
        max_digits=10, decimal_places=3, null=True, blank=True,
        verbose_name="Package Height (mm)"
    )
    pins = models.IntegerField(null=True, blank=True)
    pitch_mm = models.DecimalField(
        max_digits=10, decimal_places=3, null=True, blank=True,
        verbose_name="Pin Pitch (mm)"
    )
    
    # Description and metadata
    description = models.TextField(null=True, blank=True)
    lifecycle = models.CharField(
        max_length=10, 
        choices=LIFECYCLE_CHOICES,
        default='UNKNOWN'
    )
    rohs = models.BooleanField(null=True, blank=True)
    temp_grade = models.CharField(max_length=50, null=True, blank=True)
    
    # URLs
    url_datasheet = models.URLField(null=True, blank=True)
    url_alt = models.URLField(null=True, blank=True)
    
    # Categorization
    category_l1 = models.CharField(
        max_length=100,
        default="Unsorted",
        help_text="Primary category"
    )
    category_l2 = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text="Secondary category"
    )

    # DMT Classification
    dmtuid = models.CharField(
        max_length=20,
        unique=True,
        null=True,
        blank=True,
        help_text="Full DMT code (e.g., DMT-02030110001)"
    )
    dmt_tt = models.CharField(
        max_length=2,
        null=True,
        blank=True,
        help_text="Domain code (00-99)"
    )
    dmt_ff = models.CharField(
        max_length=2,
        null=True,
        blank=True,
        help_text="Family code (00-99)"
    )
    dmt_cc = models.CharField(
        max_length=2,
        null=True,
        blank=True,
        help_text="Class code (00-99)"
    )
    dmt_ss = models.CharField(
        max_length=2,
        null=True,
        blank=True,
        help_text="Style code (00-99)"
    )
    dmt_xxx = models.CharField(
        max_length=3,
        null=True,
        blank=True,
        help_text="Sequence number (001-999)"
    )
    
    # Integration with other tools
    footprint_name = models.CharField(max_length=255, null=True, blank=True)
    step_model_path = models.CharField(max_length=255, null=True, blank=True)
    
    # Optional JSON field for extras that don't fit in the schema
    extras = models.JSONField(null=True, blank=True)

    class Meta:
        verbose_name = "Component"
        verbose_name_plural = "Components"
        unique_together = ('manufacturer_norm', 'mpn_norm')
        indexes = [
            models.Index(fields=['mpn']),
            models.Index(fields=['manufacturer']),
            models.Index(fields=['category_l1']),
            models.Index(fields=['dmtuid']),
            models.Index(fields=['dmt_tt', 'dmt_ff', 'dmt_cc', 'dmt_ss']),
        ]
    
    def __str__(self):
        return f"{self.manufacturer} {self.mpn}"
    
    def normalize_string(self, value):
        """Normalize a string by removing extra spaces and converting to uppercase"""
        if not value:
            return value
        # Replace Unicode dashes with ASCII hyphen
        value = re.sub(r'[\u2010-\u2015]', '-', value)
        # Remove extra spaces and convert to uppercase
        return re.sub(r'\s+', ' ', value).strip().upper()

    def generate_dmtuid(self):
        """Generate DMTUID from DMT classification codes"""
        if all([self.dmt_tt, self.dmt_ff, self.dmt_cc, self.dmt_ss, self.dmt_xxx]):
            return f"DMT-{self.dmt_tt}{self.dmt_ff}{self.dmt_cc}{self.dmt_ss}{self.dmt_xxx}"
        return None

    def clean(self):
        """Normalize values before saving"""
        # Store original values
        if self.mpn:
            self.mpn_norm = self.normalize_string(self.mpn)
        if self.manufacturer:
            self.manufacturer_norm = self.normalize_string(self.manufacturer)

        # Generate DMTUID if DMT codes are present
        if not self.dmtuid and all([self.dmt_tt, self.dmt_ff, self.dmt_cc, self.dmt_ss, self.dmt_xxx]):
            self.dmtuid = self.generate_dmtuid()

        # Parse package dimensions if needed
        # This would be implemented in the importer

    def save(self, *args, **kwargs):
        """Override save to ensure normalization"""
        self.clean()
        super().save(*args, **kwargs)


class InventoryItem(TimeStampedModel):
    """
    Model representing a physical inventory item of a component.
    """
    UOM_CHOICES = (
        ('pcs', 'Pieces'),
        ('reel', 'Reel'),
        ('tube', 'Tube'),
        ('tray', 'Tray'),
    )
    
    CONDITION_CHOICES = (
        ('new', 'New'),
        ('used', 'Used'),
        ('expired', 'Expired'),
    )
    
    component = models.ForeignKey(
        Component, 
        on_delete=models.CASCADE,
        related_name='inventory_items'
    )
    quantity = models.IntegerField()
    uom = models.CharField(
        max_length=10,
        choices=UOM_CHOICES,
        default='pcs',
        verbose_name="Unit of Measure"
    )
    storage_location = models.CharField(max_length=255)
    lot_code = models.CharField(max_length=100, null=True, blank=True)
    date_code = models.CharField(max_length=100, null=True, blank=True)
    supplier = models.CharField(max_length=255, null=True, blank=True)
    price_each = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True
    )
    condition = models.CharField(
        max_length=10,
        choices=CONDITION_CHOICES,
        default='new'
    )
    note = models.TextField(null=True, blank=True)
    
    class Meta:
        verbose_name = "Inventory Item"
        verbose_name_plural = "Inventory Items"
    
    def __str__(self):
        return f"{self.component} - {self.quantity} {self.uom} at {self.storage_location}"