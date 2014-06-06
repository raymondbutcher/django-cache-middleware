from django.http import HttpResponse
from django.template import RequestContext
from django.views.decorators.cache import cache_page

from django_cache_middleware.decorators import vary_on_authentication_status


@vary_on_authentication_status
def test_authentication_status(request):
    return HttpResponse('test_authentication_status: %s' % request.user)


@cache_page(60*60*24*60)
def test_cache_page(request):
    # Cached for 60 days.
    return HttpResponse('test_cache_page')


def test_undecorated(request):
    # Ensure that the context processors aren't accessing the session.
    RequestContext(request)
    return HttpResponse('test_undecorated')
