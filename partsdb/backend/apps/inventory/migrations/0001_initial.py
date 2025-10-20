from django.db import migrations, models
import uuid


class Migration(migrations.Migration):
    
    initial = True
    
    dependencies = []
    
    operations = [
        migrations.CreateModel(
            name='Component',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('mpn', models.CharField(help_text="Manufacturer's part number", max_length=255, verbose_name='Manufacturer Part Number')),
                ('manufacturer', models.CharField(max_length=255)),
                ('value', models.CharField(blank=True, max_length=100, null=True)),
                ('tolerance', models.CharField(blank=True, max_length=50, null=True)),
                ('wattage', models.CharField(blank=True, max_length=50, null=True)),
                ('voltage', models.CharField(blank=True, max_length=50, null=True)),
                ('current', models.CharField(blank=True, max_length=50, null=True)),
                ('package_name', models.CharField(blank=True, max_length=100, null=True)),
                ('package_l_mm', models.DecimalField(blank=True, decimal_places=3, max_digits=10, null=True, verbose_name='Package Length (mm)')),
                ('package_w_mm', models.DecimalField(blank=True, decimal_places=3, max_digits=10, null=True, verbose_name='Package Width (mm)')),
                ('package_h_mm', models.DecimalField(blank=True, decimal_places=3, max_digits=10, null=True, verbose_name='Package Height (mm)')),
                ('pins', models.IntegerField(blank=True, null=True)),
                ('pitch_mm', models.DecimalField(blank=True, decimal_places=3, max_digits=10, null=True, verbose_name='Pin Pitch (mm)')),
                ('description', models.TextField(blank=True, null=True)),
                ('lifecycle', models.CharField(choices=[('ACTIVE', 'Active'), ('NRND', 'Not Recommended for New Designs'), ('EOL', 'End of Life'), ('UNKNOWN', 'Unknown')], default='UNKNOWN', max_length=10)),
                ('rohs', models.BooleanField(blank=True, null=True)),
                ('temp_grade', models.CharField(blank=True, max_length=50, null=True)),
                ('url_datasheet', models.URLField(blank=True, null=True)),
                ('url_alt', models.URLField(blank=True, null=True)),
                ('category_l1', models.CharField(default='Unsorted', help_text='Primary category', max_length=100)),
                ('category_l2', models.CharField(blank=True, help_text='Secondary category', max_length=100, null=True)),
                ('footprint_name', models.CharField(blank=True, max_length=255, null=True)),
                ('step_model_path', models.CharField(blank=True, max_length=255, null=True)),
                ('extras', models.JSONField(blank=True, null=True)),
            ],
            options={
                'verbose_name': 'Component',
                'verbose_name_plural': 'Components',
                'unique_together': {('manufacturer', 'mpn')},
                'indexes': [
                    models.Index(fields=['mpn'], name='inventory_co_mpn_554202_idx'),
                    models.Index(fields=['manufacturer'], name='inventory_co_manufac_b5b18e_idx'),
                    models.Index(fields=['category_l1'], name='inventory_co_categor_b0c6f7_idx'),
                ],
            },
        ),
        migrations.CreateModel(
            name='InventoryItem',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('quantity', models.IntegerField()),
                ('uom', models.CharField(choices=[('pcs', 'Pieces'), ('reel', 'Reel'), ('tube', 'Tube'), ('tray', 'Tray')], default='pcs', max_length=10, verbose_name='Unit of Measure')),
                ('storage_location', models.CharField(max_length=255)),
                ('lot_code', models.CharField(blank=True, max_length=100, null=True)),
                ('date_code', models.CharField(blank=True, max_length=100, null=True)),
                ('supplier', models.CharField(blank=True, max_length=255, null=True)),
                ('price_each', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ('condition', models.CharField(choices=[('new', 'New'), ('used', 'Used'), ('expired', 'Expired')], default='new', max_length=10)),
                ('note', models.TextField(blank=True, null=True)),
                ('component', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='inventory_items', to='inventory.component')),
            ],
            options={
                'verbose_name': 'Inventory Item',
                'verbose_name_plural': 'Inventory Items',
            },
        ),
    ]