import factory
from django.utils import timezone
from apps.inventory.models import Component, InventoryItem


class ComponentFactory(factory.django.DjangoModelFactory):
    """Factory for creating Component instances."""

    class Meta:
        model = Component

    mpn = factory.Sequence(lambda n: f"MPN{n}")
    manufacturer = factory.Sequence(lambda n: f"Manufacturer{n}")
    description = factory.Sequence(lambda n: f"Description for component {n}")
    package_name = factory.Faker("random_element", elements=["SOIC-8", "TSSOP-14", "SOT-23", "QFN-48"])
    url_datasheet = factory.Sequence(lambda n: f"https://example.com/datasheet{n}.pdf")
    created_at = factory.LazyFunction(timezone.now)
    updated_at = factory.LazyFunction(timezone.now)
    
    # Normalized fields will be filled by the model's save method
    
    @factory.post_generation
    def with_inventory(self, create, extracted, **kwargs):
        """Create inventory items for the component if with_inventory=True."""
        if not create or not extracted:
            return
        InventoryItemFactory(component=self, **kwargs)


class InventoryItemFactory(factory.django.DjangoModelFactory):
    """Factory for creating InventoryItem instances."""

    class Meta:
        model = InventoryItem

    component = factory.SubFactory(ComponentFactory)
    quantity = factory.Faker("random_int", min=1, max=100)
    uom = factory.Faker("random_element", elements=["pcs", "reel", "tube", "tray"])
    storage_location = factory.Faker("random_element", elements=["Rack A / Box C3", "Rack B / Box D5", "Drawer 2"])
    condition = factory.Faker("random_element", elements=["new", "used", "expired"])
    created_at = factory.LazyFunction(timezone.now)
    updated_at = factory.LazyFunction(timezone.now)