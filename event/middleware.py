import jwt
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from urllib.parse import parse_qs
from user_data.models import UserProfile
from django.contrib.auth import get_user_model
User = get_user_model()

@database_sync_to_async
def get_user_by_id(user_id):
    try:
        return User.objects.get(id=user_id)
    except User.DoesNotExist:
        return None


@database_sync_to_async
def get_user_by_username(username):
    try:
        return User.objects.get(username=username)
    except User.DoesNotExist:
        return None


class JWTAuthMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send):
        from django.contrib.auth.models import User
        query_string = scope.get("query_string", b"").decode()
        query_params = parse_qs(query_string)
        token = query_params.get("token", [None])[0]
        url_username = scope.get("path", "").split("/")[-2]  # extract username from ws/chat/<username>/

        user = AnonymousUser()

        if token:
            try:
                payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
                user_id = payload.get("user_id")

                # Fetch user by ID
                user_from_token = await get_user_by_id(user_id)

                # Also verify the URL username matches the token's user
                if user_from_token and user_from_token.username == url_username:
                    user = user_from_token
                else:
                    print(f"[SECURITY] Username mismatch! Token user: {user_from_token.username if user_from_token else 'None'} | URL user: {url_username}")
            except Exception as e:
                print(f"[JWTAuth] Token invalid or user mismatch: {e}")

        scope["user"] = user
        return await super().__call__(scope, receive, send)
