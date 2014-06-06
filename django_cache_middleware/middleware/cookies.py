import re

from django.conf import settings
from django.core.exceptions import MiddlewareNotUsed


def get_cookie_patterns(cookie_names):
    for name in cookie_names:
        yield r'%s=.+?(?:; |$)\w*' % name


def compile_cookie_patterns(cookie_names):
    patterns = get_cookie_patterns(cookie_names)
    patterns = ('(%s)' % pattern for pattern in patterns)
    return re.compile('|'.join(patterns))


class StripCookiesMiddleware(object):
    """
    Remove cookies from the request so they don't affect caching.

    It is recommended to strip all cookies that are not accessed by your
    Django application. Javascript can still read cookies that have been
    stripped at the server level.

    Note: Stripping cookies won't affect the user at all unless your Django
    application needs to access their values. In that case - don't strip them!

    Taken and modified from http://djangosnippets.org/snippets/1772/

    """

    def __init__(self):
        allowed_cookies = getattr(settings, 'ALLOWED_COOKIE_NAMES', None)
        if allowed_cookies:
            self.allowed_cookies = compile_cookie_patterns(allowed_cookies)
        else:
            strip_cookies = getattr(settings, 'STRIP_COOKIE_NAMES', None)
            if strip_cookies:
                self.strip_cookies = compile_cookie_patterns(strip_cookies)
            else:
                raise MiddlewareNotUsed()

    def process_request(self, request):
        if 'HTTP_COOKIE' in request.META:
            if hasattr(self, 'allowed_cookies'):
                cookies = []
                for match in self.allowed_cookies.finditer(request.META['HTTP_COOKIE']):
                    cookies.append(match.group(0))
                cleaned_cookies = ';'.join(cookies)
            else:
                cleaned_cookies = self.strip_cookies.sub('', request.META['HTTP_COOKIE'])
            request.META['HTTP_COOKIE'] = cleaned_cookies
