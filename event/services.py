from django.conf import settings
import time
import jwt
from dataclasses import dataclass
from django.core.exceptions import ImproperlyConfigured
from rest_framework import serializers
from connectify_bulk_hiring import settings
@dataclass
class ZoomSignatureResult:
    signature: str
    issued_at: int
    expires_at: int


class ZoomSignatureService:
    DEFAULT_TTL_SECONDS = 60 * 60 * 2  # 2 hours

    def __init__(self, sdk_key: str = None, sdk_secret: str = None):
        self.sdk_key = settings.ZOOM_SDK_CLIENT_ID
        self.sdk_secret = settings.ZOOM_SDK_CLIENT_SECRET
        if not self.sdk_key or not self.sdk_secret:
            raise ImproperlyConfigured("ZOOM_SDK_KEY / ZOOM_SDK_SECRET not set in settings.")

    def generate(self, meeting_number: str, role: int = 0, ttl_seconds: int = None) -> ZoomSignatureResult:
        """
        meeting_number: Zoom meeting number as string
        role: 0=attendee, 1=host (Zoom Meeting SDK convention)
        ttl_seconds: override TTL (defaults to 2h)
        """
        ttl = ttl_seconds or self.DEFAULT_TTL_SECONDS
        iat = int(time.time()) - 30
        exp = iat + ttl

        header = {
            "alg":"HS256",
            "typ":"JWT"
        }

        payload = {
            "appKey": self.sdk_key,
            "mn": meeting_number,
            "role": role,
            "iat": iat,
            "exp": exp,
            "tokenExp": exp,
        }

        token = jwt.encode(payload=payload, key=self.sdk_secret, algorithm="HS256")
        if not isinstance(token, str):
            token = token.decode("utf-8")

        return ZoomSignatureResult(signature=token, issued_at=iat, expires_at=exp)