from django.core.cache import cache as cache_backend
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpResponseNotModified, HttpResponseForbidden
from django.middleware import cache as original
from django.utils.cache import get_max_age, patch_response_headers

from django_cache_middleware.middleware.utils import (
    generate_cache_key,
    get_cached_headers,
    has_vary_header,
    learn_cache_key,
    not_modified,
)


class UpdateCacheMiddleware(original.UpdateCacheMiddleware):
    """
    Response-phase cache middleware that updates the cache if the response is
    cacheable.

    This code is identical to Django's version except that it uses a different
    learn_cache_key function.

    Differences from the Django version:
    * Caches the full URL including host and querystring.
    * Caches extra data to support returning "304 Not Modified" responses.
    * Caches extra data to support the "Vary-On-View" header.

    """

    def _should_update_cache(self, request, response):
        """Copied from Django 1.2.5 with no changes made."""
        if not hasattr(request, '_cache_update_cache') or not request._cache_update_cache:
            return False
        if self.cache_anonymous_only and has_vary_header(response, 'Cookie'):
            if not hasattr(request, 'user'):
                raise ImproperlyConfigured(
                    "The Django cache middleware with CACHE_MIDDLEWARE_ANONYMOUS_ONLY=True "
                    "requires authentication middleware to be installed. Edit your MIDDLEWARE_CLASSES "
                    "setting to insert 'django.contrib.auth.middleware.AuthenticationMiddleware' "
                    "before the CacheMiddleware."
                )
            if request.user.is_authenticated():
                # Don't cache user-variable requests from authenticated users.
                return False
        return True

    def process_response(self, request, response):

        if getattr(request, 'response_has_esi', False):
            response['Has-ESI'] = True

        if response.has_header('ETag') and not response['ETag']:
            del response['ETag']

        if not self._should_update_cache(request, response):
            # We don't need to update the cache, just return.
            return response

        if request.method != 'GET':
            return response

        if response.status_code != 200:
            return response

        if not response._is_string:
            # Cannot cache iterable/streamed responses.
            return response

        timeout = get_max_age(response)
        if timeout is None:
            timeout = self.cache_timeout
        elif timeout == 0:
            # max-age was set to 0, don't bother caching.
            return response

        patch_response_headers(response, timeout)

        if timeout:
            cache_key = learn_cache_key(request, response, timeout, self.key_prefix)
            cache_backend.set(cache_key, response, timeout)

        return response


class FetchFromCacheMiddleware(original.FetchFromCacheMiddleware):
    """
    Request-phase cache middleware that fetches a page from the cache.

    Differences from the Django version:
    * Caches the full URL including host and querystring.
    * Returns a "304 Not Modified" response when Etag or Last-Modified matches.
    * When the "Vary-On-View" header is found, calls the view's vary_on_view
      function to allow specific caching rules at the view level.

    """

    def _process_headers(self, request, headers):

        cache_key = generate_cache_key(request, headers, self.key_prefix)
        if cache_key is None:
            # No cache information available, need to rebuild.
            request._cache_update_cache = True
            return

        response = cache_backend.get(cache_key, None)
        if response is None:
            # No cache information available, need to rebuild.
            request._cache_update_cache = True
            return None

        # Check the Etag/Last-Modified headers of the cache response.
        etag = response.has_header('Etag') and response['Etag']
        last_modified = response.has_header('Last-Modified') and response['Last-Modified']
        if not_modified(request, etag, last_modified):
            # Nothing changed since they last downloaded it.
            request._cache_update_cache = False
            return HttpResponseNotModified()

        request._cache_update_cache = False
        response['X-From-Cache'] = True
        return response

    def process_request(self, request):

        if request.method == 'PURGE':
            # TODO: check request IP address against a setting
            if False:
                request.method = 'GET'
                request._cache_update_cache = True
                request._purging = True
                return
            else:
                request._cache_update_cache = False
                return HttpResponseForbidden('Your address is now allowed to make purge requests.')

        if request.method not in ('GET', 'HEAD') or request.is_secure():
            # Don't bother checking the cache.
            request._cache_update_cache = False
            return

        headers = get_cached_headers(request, self.key_prefix)
        if headers is None:
            # No cache information available, need to rebuild.
            request._cache_update_cache = True
            return

        if 'X-Vary-On-View' in headers:
            # Handle this request during the process_view phase.
            request._cache_middleware_headers = headers
            return

        # There is no vary, so we can check the Etag/Last-Modified headers.
        # Make sure that these headers are popped off the dictionary, because
        # they were not used when generating the response cache key.
        etag = headers.pop('HTTP_ETAG', None)
        last_modified = headers.pop('HTTP_LAST_MODIFIED', None)
        if not_modified(request, etag, last_modified):
            # Nothing changed since they last downloaded it.
            request._cache_update_cache = False
            return HttpResponseNotModified()

        # Try to return a cached response, using the request + cached headers.
        return self._process_headers(request, headers)

    def process_view(self, request, view_func, view_args, view_kwargs):

        if not hasattr(request, '_cache_middleware_headers'):
            return

        if not hasattr(view_func, '_vary_on_view'):
            return

        headers = request._cache_middleware_headers
        value = view_func._vary_on_view(request, *view_args, **view_kwargs)
        headers['X-Vary-On-View'] = value

        # Try to return a cached response, using the request + cached headers.
        return self._process_headers(request, headers)


class CacheMiddleware(UpdateCacheMiddleware, FetchFromCacheMiddleware, original.CacheMiddleware):
    """
    Cache middleware that provides basic behavior for many simple sites.

    Differences from the Django version:
    * Caches the full URL including host and querystring.
    * Caches extra data to support returning "304 Not Modified" responses.
    * Returns a "304 Not Modified" response when Etag or Last-Modified matches.
    * Caches extra data to support the "Vary-On-View" header.
    * When the "Vary-On-View" header is found, calls the view's vary_on_view
      function to allow specific caching rules at the view level.

    """
