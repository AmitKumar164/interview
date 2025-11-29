"""
ASGI config for connectify project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information, see
https://docs.djangoproject.com/en/5.2/howto/deployment/asgi/
"""

import os
import django
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter

# ✅ Set DJANGO_SETTINGS_MODULE before anything else
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'connectify_bulk_hiring.settings')

# ✅ Initialize Django
django.setup()

# ✅ Import after Django setup
from event.middleware import JWTAuthMiddleware
from event.routing import websocket_urlpatterns

# HTTP application
django_asgi_app = get_asgi_application()

# Main ASGI application
application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": JWTAuthMiddleware(
        URLRouter(websocket_urlpatterns)
    ),
})
