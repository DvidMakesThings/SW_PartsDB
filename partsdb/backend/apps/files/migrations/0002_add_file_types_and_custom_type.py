# Generated migration for files app - add new file types and custom_type field

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('files', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='attachment',
            name='custom_type',
            field=models.CharField(blank=True, help_text='Custom file type when "Other" is selected', max_length=100, null=True),
        ),
        migrations.AlterField(
            model_name='attachment',
            name='type',
            field=models.CharField(choices=[('datasheet', 'Datasheet'), ('three_d', '3D Model (STEP)'), ('eagle_lib', 'Eagle Library'), ('photo', 'Photo'), ('appnote', 'Application Note'), ('schematic', 'Schematic'), ('layout', 'Layout/PCB'), ('other', 'Other')], max_length=20),
        ),
    ]
