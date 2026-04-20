from django.utils import timezone
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from .models import APIToken, APITokenUsageLog


class APITokenAuthentication(BaseAuthentication):
    def authenticate(self, request):
        auth_header = request.headers.get("Authorization")

        if not auth_header:
            return None

        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != "token":
            raise AuthenticationFailed("Invalid token format. Use: Token <token>")

        token_key = parts[1]

        try:
            token = APIToken.objects.get(token=token_key, is_active=True)
        except APIToken.DoesNotExist:
            raise AuthenticationFailed("Invalid or revoked token")

        now = timezone.now()
        token.last_used_at = now
        token.usage_count += 1
        token.save(update_fields=["last_used_at", "usage_count"])

        APITokenUsageLog.objects.create(
            token=token,
            called_at=now,
            endpoint=request.path,
        )

        return (None, token)