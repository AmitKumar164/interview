import os
from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "connectify_bulk_hiring.settings")

app = Celery("connectify_bulk_hiring")

app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
