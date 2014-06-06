import datetime

from django.conf import settings
from django.core.cache import cache
from django.utils.cache import cc_delim_re, _i18n_cache_key_suffix
from django.utils.encoding import iri_to_uri
from django.utils.hashcompat import md5_constructor

from email.Utils import parsedate


def _generate_cache_header_key(key_prefix, request):
    """
    Returns a cache key for the header cache.
    NOTE: This includes the querystring in the URL.

    """
    url = md5_constructor()
    url.update(request.get_host())
    url.update(iri_to_uri(request.get_full_path()))
    cache_key = 'cache_middleware.headers.%s.%s' % (key_prefix, url.hexdigest())
    return _i18n_cache_key_suffix(request, cache_key)


def generate_cache_key(request, headers, key_prefix=None):
    """
    Returns a cache key from the headers given in the header list.
    NOTE: This was copied from Django, with the following changes:
    * Caches based on full path, including the query string.
    * Requires headers as a dictionary, which can optionally contain values
      for the headers. When provided, these values are used instead of the
      request header values. This is to support including the X-Vary-On-View
      header values in the cache key.

    """
    if key_prefix is None:
        key_prefix = settings.CACHE_MIDDLEWARE_KEY_PREFIX
    ctx = md5_constructor()
    for header, value in sorted(headers.items()):
        if value is None:
            value = request.META.get(header, None)
            if value is not None:
                ctx.update(value)
        else:
            ctx.update(value)
    url = md5_constructor()
    url.update(request.get_host())
    url.update(iri_to_uri(request.get_full_path()))
    cache_key = 'cache_middleware.response.%s.%s.%s' % (key_prefix, url.hexdigest(), ctx.hexdigest())
    return _i18n_cache_key_suffix(request, cache_key)


def get_cached_headers(request, key_prefix=None):
    """Returns the cached headers list for a given request's path."""
    if key_prefix is None:
        key_prefix = settings.CACHE_MIDDLEWARE_KEY_PREFIX
    cache_key = _generate_cache_header_key(key_prefix, request)
    return cache.get(cache_key, None)


def learn_cache_key(request, response, cache_timeout=None, key_prefix=None):
    """
    NOTE: This was copied from Django, with the following changes:
    * Caches based on full path, including the query string.
    * Stores the ETag and Last-Modified headers to support responding with
      "304 Not Modified" responses.
    * Supports custom "X-Vary-On-View" headers that can be used instead of the
      cookie header in the cache key for a response. This provides more control
      over what is cached, without altering the actual response.

    Learns what headers to take into account for some request path from the
    response object. It stores those headers in a global path registry so that
    later access to that path will know what headers to take into account
    without building the response object itself. The headers are named in the
    Vary header of the response, but we want to prevent response generation.

    The list of headers to use for cache key generation is stored in the same
    cache as the pages themselves. If the cache ages some data out of the
    cache, this just means that we have to build the response once to get at
    the Vary header and so at the list of headers to use for the cache key.

    """

    if key_prefix is None:
        key_prefix = settings.CACHE_MIDDLEWARE_KEY_PREFIX

    if cache_timeout is None:
        cache_timeout = settings.CACHE_MIDDLEWARE_SECONDS

    # Get the Vary headers, to build a cache key for this response. For
    # example, a response that varies on cookie would result in multiple
    # cached responses; one for each cookie value that is encountered. This
    # dictionary is effectively a list, as it does not have any values.
    response_headers = {}
    if response.has_header('Vary'):
        for header in cc_delim_re.split(response['Vary']):
            response_headers['HTTP_' + header.upper().replace('-', '_')] = None

    if response.has_header('X-Vary-On-View'):
        # When available, use the Vary-On-View header instead of the Cookie.
        response_headers['X-Vary-On-View'] = response['X-Vary-On-View']
        if 'HTTP_COOKIE' in response_headers:
            del response_headers['HTTP_COOKIE']
        key_headers = response_headers
    else:
        # When there is no vary on view, we can store the Etags/Last-Modified
        # values in the header list. Nothing varies, so we can be sure that
        # the values are not for a different version of the page. This avoids
        # fetching the response for no reason.
        key_headers = {}
        if response.has_header('Etag'):
            key_headers['HTTP_ETAG'] = response['Etag']
        if response.has_header('Last-Modified'):
            key_headers['HTTP_LAST_MODIFIED'] = response['Last-Modified']
        key_headers.update(response_headers)

    # Cache this list of headers against this request URL.
    # This is the "global path registry" that everyone is talking about.
    cache_key = _generate_cache_header_key(key_prefix, request)
    cache.set(cache_key, key_headers, cache_timeout)

    # Generate a cache key for this response. This will be based on the
    # request path and the request HTTP header values (the vary ones).
    return generate_cache_key(request, response_headers, key_prefix)


def parse_http_date(date_string):
    """
    Converts a HTTP datetime string into a Python datatime object.
    Doesn't support every single format, but it's good enough.

    """
    try:
        return datetime.datetime(*parsedate(date_string)[:6])
    except:
        return None


def not_modified(request, etag=None, last_modified=None):
    """
    Compares the request against the Etag/Last-Modified headers, to determine
    if the content was modified since the client last downloaded it.

    """

    if 'HTTP_IF_NONE_MATCH' in request.META:
        if etag:
            client = request.META['HTTP_IF_NONE_MATCH']
            server = etag
            if client.strip('"') == server.strip('"'):
                return True
            return False

    if 'HTTP_IF_MODIFIED_SINCE' in request.META:
        if last_modified:
            client = request.META['HTTP_IF_MODIFIED_SINCE'].split(';')[0].strip()
            server = last_modified
            if client == server:
                return True
            if parse_http_date(server) <= parse_http_date(client):
                return True
        return False

    return False


def has_vary_header(response, header_query):
    """
    Checks to see if the response has a given header name in its Vary header.
    Copied from Django 1.2.5 so we can use it in Django 1.2.4
    """
    if not response.has_header('Vary'):
        return False
    vary_headers = cc_delim_re.split(response['Vary'])
    existing_headers = set([header.lower() for header in vary_headers])
    return header_query.lower() in existing_headers
