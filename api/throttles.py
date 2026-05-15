from rest_framework.throttling import SimpleRateThrottle


class APITokenThrottle(SimpleRateThrottle):
    """
    Per-token rate limiter. Uses the APIToken PK as the cache key so each
    pharmacy token gets its own quota independent of IP address.

    Rate limit is read from SystemConfig.api_token_rate_limit at request time
    so changes take effect without a deploy (within the cache TTL window).

    Falls through (returns None) for requests with no auth token, which
    means unauthenticated requests are blocked by HasAPIToken before throttle.
    """
    scope = "api_token"

    def get_cache_key(self, request, view):
        token = getattr(request, "auth", None)
        if token is None:
            return None
        return self.cache_format % {"scope": self.scope, "ident": token.pk}

    def get_rate(self):
        try:
            from django.apps import apps
            SystemConfig = apps.get_model("control", "SystemConfig")
            limit = SystemConfig.get().api_token_rate_limit
            if limit == 0:
                # 0 = unlimited — return None to disable throttling entirely
                return None
            return f"{limit}/hour"
        except Exception:
            # Fallback to the static settings value if DB is unavailable
            return super().get_rate()
