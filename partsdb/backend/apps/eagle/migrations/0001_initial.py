from django.db import migrations, models
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('inventory', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='EagleLink',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('eagle_library', models.CharField(max_length=255)),
                ('eagle_device', models.CharField(max_length=255)),
                ('eagle_package', models.CharField(max_length=255)),
                ('notes', models.TextField(blank=True, null=True)),
                ('component', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='eagle_links', to='inventory.component')),
            ],
            options={
                'verbose_name': 'Eagle Link',
                'verbose_name_plural': 'Eagle Links',
                'unique_together': {('component', 'eagle_library', 'eagle_device')},
            },
        ),
    ]