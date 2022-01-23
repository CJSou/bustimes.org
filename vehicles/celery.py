import os
import ssl
from celery import Celery


os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'buses.settings')

app = Celery('vehicles')

app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django app configs.
app.autodiscover_tasks()
