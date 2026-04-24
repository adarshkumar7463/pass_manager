from django.core.cache import cache
from django.http import JsonResponse
from django.conf import settings


class RateLimitMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith('/generate-pass/') and request.method == 'POST':
            ip = self._get_ip(request)
            key = f"ratelimit:{ip}"
            count = cache.get(key, 0)
            limit = getattr(settings, 'RATE_LIMIT_REQUESTS', 5)
            window = getattr(settings, 'RATE_LIMIT_WINDOW', 3600)
            if count >= limit:
                return JsonResponse({'error': 'Rate limit exceeded. Try again later.'}, status=429)
            cache.set(key, count + 1, window)
        return self.get_response(request)

    def _get_ip(self, request):
        xff = request.META.get('HTTP_X_FORWARDED_FOR')
        return xff.split(',')[0].strip() if xff else request.META.get('REMOTE_ADDR', '0.0.0.0')
