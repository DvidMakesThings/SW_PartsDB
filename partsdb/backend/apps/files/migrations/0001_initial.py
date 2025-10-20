from django.db import migrations, models
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('inventory', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Attachment',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('type', models.CharField(choices=[('datasheet', 'Datasheet'), ('three_d', '3D Model'), ('photo', 'Photo'), ('appnote', 'Application Note'), ('other', 'Other')], max_length=20)),
                ('file', models.FileField(upload_to='uploads/')),
                ('source_url', models.URLField(blank=True, null=True)),
                ('sha256', models.CharField(blank=True, db_index=True, max_length=64, null=True)),
                ('component', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='attachments', to='inventory.component')),
            ],
            options={
                'verbose_name': 'Attachment',
                'verbose_name_plural': 'Attachments',
                'indexes': [
                    models.Index(fields=['type'], name='files_attac_type_b2e44c_idx'),
                    models.Index(fields=['sha256'], name='files_attac_sha256_ef7458_idx'),
                ],
            },
        ),
    ]