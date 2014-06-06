import sys

from django.conf import settings
from django.core.exceptions import MiddlewareNotUsed
from django.utils.cache import get_max_age
from django.views.debug import technical_500_response

from django_cache_middleware.middleware.utils import has_vary_header


class InvalidHeadersWarning(Exception):
    pass


def handle_uncaught_exception(process_response):
    def safe_process_response(self, request, response):
        try:
            return process_response(self, request, response)
        except Exception:
            return technical_500_response(request, *sys.exc_info())
    return safe_process_response


class StrictHeadersMiddleware(object):
    """
    Ensures that the HTTP headers for each response suit our chosen
    approaches to caching.

    If intending to keep using CacheMiddleware:
        Place this above the caching middleware.
    Otherwise:
        Place this below the caching middleware.

    """

    # Some built-in views have no caching headers, but don't cause any issues.
    # Don't bother checking the headers for these paths.
    # TODO: make a setting for this
    ignored_paths = (
    )

    def __init__(self):
        if not settings.DEBUG:
            raise MiddlewareNotUsed

    @staticmethod
    def _assert_cache_anonymous_only(request, response):
        """
        Assert that we only do caching for anonymous users.
        This is pretty tricky and not everything is being checked.
        This is only used by Finda Social which is defunct; so nobody cares.

        Good decorators to use:
            from django_cache_middleware.decorators import add_cache_headers
            from django.views.decorators.cache import never_cache

        """

        # We are allowed to access the user here, because the code that calls
        # this method only runs when the session has already been accessed
        # and/or the Vary: Cookie header was already added.
        if request.user.is_authenticated():

            # It is tricky to check that a response hasn't been added to the
            # cache, but we can check that it hasn't been fetched from there.
            assert 'X-From-Cache' not in response, 'You are logged in but it somehow served you a cached page.'

            # Ensure that the vary header is there. If not, then the middleware
            # is in the wrong order and things will be crazy.
            assert has_vary_header(response, 'Cookie'), 'The "Vary: Cookie" header was not set, even though your cookie was accessed.'

    @staticmethod
    def _assert_has_headers(response):
        """
        Assert that we have the standard caching headers.

        Good decorators to use:
            from django_cache_middleware.decorators import add_cache_headers
            from django.views.decorators.cache import never_cache

        """

        # A max-age value must be set.
        # A value of 0 is acceptable.
        max_age_header = get_max_age(response)
        assert max_age_header is not None

        # And check for the other ones too.
        for header in ('ETag', 'Last-Modified', 'Expires'):
            assert header in response

    @staticmethod
    def _assert_not_cached(response):
        """
        Assert that the the max-age header is defined and set to 0,
        or that has a custom vary-on-view header.

        Good decorator to use:
            from django.views.decorators.cache import never_cache

        """

        max_age_header = get_max_age(response)
        assert (max_age_header == 0) or ('X-Vary-On-View' in response)

    @classmethod
    def _typical_get_request(cls, request, response):

        if request.method in ('GET', 'HEAD'):
            if not request.is_secure():
                return True

        return False

    @handle_uncaught_exception
    def process_response(self, request, response):

        # Some built in django views have no caching headers. Ignore them.
        for path in self.ignored_paths:
            if request.path.startswith(path):
                return response

        if response.status_code == 304:
            # Not Modified responses don't need to be checked. They will
            # sometimes have unwanted headers at this point, which Django
            # will remove later on in the base handler.
            return response

        if not self._typical_get_request(request, response):
            # These types of requests/responses should never be cached, and
            # thus should not have caching headers in the response.
            # If they do have cache headers, then they must be "never cache"
            # headers (a max-age of 0).
            if get_max_age(response) not in (0, None):
                raise InvalidHeadersWarning('Only non-secure GET/HEAD requests should have caching headers.')
            else:
                return response

        if response.status_code != 200:
            # We generally only cache responses with a status code of 200,
            # but there are exceptions. As long as the other checks are done
            # then this is OK to let through.
            return response

        # All typical GET requests must have some caching headers defined.
        try:
            self._assert_has_headers(response)
        except AssertionError:
            message = (
                "This URL does not have the required caching headers. "
                "Typical GET requests must return a response with caching headers defined at the view level. "
                "The current headers are: %s"
            )
            header_list = [': '.join(header) for header in response._headers.values()]
            headers = ', '.join(header_list)
            raise InvalidHeadersWarning(message % headers)

        session_was_accessed = hasattr(request, 'session') and request.session.accessed

        if session_was_accessed or has_vary_header(response, 'Cookie'):

            if settings.CACHE_MIDDLEWARE_ANONYMOUS_ONLY:
                # When using this setting, all of the requirements for headers
                # have changed. This is just for Finda Social, which has very
                # different caching rules than the other sites.
                try:
                    self._assert_cache_anonymous_only(request, response)
                except AssertionError, error:
                    raise InvalidHeadersWarning('CACHE_MIDDLEWARE_ANONYMOUS_ONLY is enabled and the following occurred: %s' % error)
                else:
                    return response

            if session_was_accessed:
                message_info = "accessed the user's session (probably by simply accessing request.user)"
            else:
                message_info = "returned a response with the Vary: Cookie header"
            message = "This URL has %s, but the response still has standard caching headers. You can't do both!" % message_info

            # If the session has been accessed and/or the "Vary: Cookie" header
            # exists, then the HTTP headers should specify that the response
            # is not to be cached.
            try:
                self._assert_not_cached(response)
            except AssertionError:
                raise InvalidHeadersWarning(message)

        return response
