from django.urls import re_path
from .consumers import ConnectifyConsumer

websocket_urlpatterns = [
    re_path(r'ws/connectify_bulk_hiring/(?P<session_id>\d+)/(?P<username>[^/]+)/$', ConnectifyConsumer.as_asgi()),
]
