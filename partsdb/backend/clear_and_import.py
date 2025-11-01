import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'partsdb.settings')
django.setup()

from apps.inventory.models import Component

# Delete all existing components
count = Component.objects.count()
print(f'Deleting {count} existing components...')
Component.objects.all().delete()
print('Database cleared!')

# Now run the import
import subprocess
result = subprocess.run(['python', 'manage.py', 'import_csv', '../_csv_renderer/DMT_Partslib.csv'])
print(f'\nImport completed with exit code: {result.returncode}')
