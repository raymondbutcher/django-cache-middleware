from django.conf import settings
from django.core.cache import cache
from django.utils.cache import patch_response_headers, add_never_cache_headers, get_max_age
from django.utils.decorators import method_decorator
from django.utils.functional import wraps

from django_cache_middleware.decorators.utils import _combine_functions, _quotify_function


def add_cache_headers(cache_timeout=None, method=False):
    """
    Adds some useful headers to the given HttpResponse object:
        ETag, Last-Modified, Expires and Cache-Control

    Each header is only added if it isn't already set.

    cache_timeout is in seconds.
    The CACHE_MIDDLEWARE_SECONDS setting is used by default.

    """

    # Allow the decorator to be called with or without
    # the cache_timeout argument.
    if callable(cache_timeout):
        viewfunc = cache_timeout
        cache_timeout = None
    else:
        viewfunc = None

    def decorator(viewfunc):
        @wraps(viewfunc)
        def patched_view(request, *args, **kwargs):

            if settings.CACHE_MIDDLEWARE_ANONYMOUS_ONLY:
                # If the site is using the cache middleware, and it is set
                # to only cache for anonymous users, then we will check their
                # authentication status. This works because the middleware
                # supports the vary_on_view decorators.
                authenticated = request.user.is_authenticated()
            else:
                # This is the normal use-case. We want to avoid accessing the
                # request.user object as much as possible. Set authenticated
                # to None to indicate that we did not even check.
                authenticated = None

            if authenticated is False and not hasattr(viewfunc, '_vary_on_view'):
                # If we did check the user's authentication status, and found
                # that they are anonymous, then we want ensure that we are
                # using a "vary on view" decorator. If it was not defined
                # specifically on the view, then we can assume that we just
                # need to cache all anonymous users exactly the same. For this,
                # the vary_on_authentication_status can be used.
                response = vary_on_authentication_status(viewfunc)(request, *args, **kwargs)
            else:
                # If we did not check the authentication status, or we did
                # check and found that they are authenticated, then we can
                # just use the view as it is.
                response = viewfunc(request, *args, **kwargs)

            if request.method != 'GET':
                return response
            if response.status_code != 200:
                return response
            if request.is_secure():
                return response

            if authenticated is True:
                # We checked if the user is authenticated, and they were,
                # so do not cache the response.
                add_never_cache_headers(response)
            else:
                # Either the user is not authenticated, or we did not check.
                # In either case, add the caching headers.
                patch_response_headers(response, cache_timeout=cache_timeout)

            return response

        return patched_view

    if method:
        decorator = method_decorator(decorator)

    if viewfunc:
        return decorator(viewfunc)
    else:
        return decorator


def simple_response_cache(view_func):
    """
    This does not use any site-specific cache keys, so only use it where the
    response does not vary by site. Place this above add_cache_headers
    when decorating a view.

    """

    @wraps(view_func)
    def wrapped_view(request, *args, **kwargs):

        # Build a cache key using only the view function and the arguments;
        # nothing related to the request or current site.
        view_path = '.'.join((view_func.__module__, view_func.__name__))
        signature = HashableTuple((args, kwargs)).hash
        cache_key = ':'.join((view_path, signature))

        # Retrieve the response from the cache, or generate a new one.
        if getattr(request, '_purging', False):
            response = None
        else:
            response = cache.get(cache_key)
        if response is None:
            response = view_func(request, *args, **kwargs)
            max_age = get_max_age(response)
            if max_age is not None:
                cache.set(cache_key, response, max_age)
        else:
            response['X-From-Cache'] = True

        # Stop the middleware from caching it too.
        request._cache_update_cache = False

        return response

    return wrapped_view


def cache_upstream(cache_timeout=None):
    """
    Add HTTP cache headers to responses, but do not actually cache them.
    Use this to cache a URL in Varnish but not the page-level cache.

    """

    # Allow the decorator to be called with or without
    # the cache_timeout argument.
    if callable(cache_timeout):
        viewfunc = cache_timeout
        cache_timeout = None
    else:
        viewfunc = None

    def decorator(viewfunc):

        @wraps(viewfunc)
        def patched_view(request, *args, **kwargs):
            response = viewfunc(request, *args, **kwargs)
            patch_response_headers(response, cache_timeout=cache_timeout)
            request._cache_update_cache = False
            return response

        return patched_view

    if viewfunc:
        return decorator(viewfunc)
    else:
        return decorator


def vary_on_view(value_func):
    """
    A view decorator that allows the cache middleware to cache responses on
    a per-request basis, using the result of the value_func to generate the
    response's cache key.

    The argument "value_func" must be a view-like function that accepts the
    same arguments as the view that is being decorated. It must return a value
    to be used in the response's cache key.

    This decorator adds a custom response header, which the cache middleware
    will use when generating the response's cache key.

    If the response has Vary:Cookie set in its headers (it probably will if
    vary_on_view is needed), the cache middleware will ignore the cookie value
    when generating the response's cache key. The actual response is not
    affected, which allows the client to do its own caching as usual.

    """

    value_func = _quotify_function(value_func)

    def decorator(func):

        # Build the decorated view that adds the custom response header.
        def inner(request, *args, **kwargs):
            response = func(request, *args, **kwargs)
            if response.status_code == 200:
                if not response.has_header('X-Vary-On-View'):
                    response['X-Vary-On-View'] = ''
                response['X-Vary-On-View'] += value_func(request, *args, **kwargs)
            return response

        # Attach the value_func to the view for the middlware to use. Support
        # nested usage of this decorator by making it return a combined list.
        if hasattr(func, '_vary_on_view'):
            inner._vary_on_view = _combine_functions(func._vary_on_view, value_func)
        else:
            inner._vary_on_view = value_func

        return inner
    return decorator


@vary_on_view
def vary_on_authentication_status(request, *args, **kwargs):
    """
    All authenticated users share a single cached response.
    All anonymous users share a single cached response.

    """
    return request.user.is_authenticated()


@vary_on_view
def vary_on_staff_status(request, *args, **kwargs):
    """
    All staff members share a single cached response.
    All other users share a single cached response.

    """

    return request.user.is_staff


@vary_on_view
def vary_on_user_type(request, *args, **kwargs):
    """
    All staff members share a single cached response.
    All regular users share a single cached response.
    All anonymous users share a single cached response.

    """

    return int(request.user.is_authenticated()) + int(request.user.is_staff)


@vary_on_view
def vary_on_user_id(request, *args, **kwargs):
    """
    Authenticated users each have their own cached response.
    All anonymous users share a single cached response.

    Avoids caching individual responses for anonymous users when
    your view gives all anonymous users the same response.
    """

    if request.user.is_authenticated():
        return request.user.id
    else:
        return 0
