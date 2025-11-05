"""
Celery configuration for partsdb project.
"""

import os

from celery import Celery

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'partsdb.settings')

app = Celery('partsdb')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django app configs.
app.autodiscover_tasks()

# Task will run synchronously if Redis is not available
app.conf.task_always_eager = not os.environ.get('REDIS_URL', None)