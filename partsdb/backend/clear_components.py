#!/usr/bin/env python
"""Clear all components from the database"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'partsdb.settings')
django.setup()

from apps.inventory.models import Component

count = Component.objects.count()
print(f'Found {count} components in database')
confirm = input('Delete all components? (yes/no): ')

if confirm.lower() == 'yes':
    Component.objects.all().delete()
    print('All components deleted!')
    print('\nNow run: python manage.py import_csv ../_csv_renderer/DMT_Partslib.csv')
else:
    print('Operation cancelled')
