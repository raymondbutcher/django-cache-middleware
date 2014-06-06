"""
Oh ho ho, swap out the middleware. This is done so that
Django's @cache_page decorator works with this new middleware.

"""

from django.middleware import cache
import middleware as improved

cache.UpdateCacheMiddleware = improved.UpdateCacheMiddleware
cache.FetchFromCacheMiddleware = improved.FetchFromCacheMiddleware
cache.CacheMiddleware = improved.CacheMiddleware

from django.views.decorators import cache
cache.CacheMiddleware = improved.CacheMiddleware

