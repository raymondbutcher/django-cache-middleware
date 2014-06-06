from django.conf.urls.defaults import *

urlpatterns = patterns(
    'django_cache_middleware.tests.views',
    (r'^test_authentication_status/', 'test_authentication_status'),
    (r'^test_cache_page/', 'test_cache_page'),
    (r'^test_undecorated/', 'test_undecorated'),
)
