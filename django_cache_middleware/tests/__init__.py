import datetime
import time

from django.conf import settings
from django.contrib.auth.models import User
from django.test import TestCase

from django_cache_middleware.utils import parse_http_date


class CacheMiddlewareTests(TestCase):

    urls = 'django_cache_middleware.tests.urls'

    def setUp(self):
        self.cache_middleware_seconds = settings.CACHE_MIDDLEWARE_SECONDS
        settings.CACHE_MIDDLEWARE_SECONDS = 60 * 5

    def tearDown(self):
        settings.CACHE_MIDDLEWARE_SECONDS = self.cache_middleware_seconds

    def test_authentication_status(self):

        User.objects.create_user(username='testuser1', email='', password='test')
        User.objects.create_user(username='testuser2', email='', password='test')

        # Use the current time to make a URL that won't have been cached before.
        url = '/test_authentication_status/?time=%s' % time.time()

        # Fetch the page as an anonymous user.
        response = self.client.get(url)
        self.assertTrue(response.has_header('Vary'))
        self.assertFalse(response.has_header('X-From-Cache'))
        self.assertTrue(response.has_header('X-Vary-On-View'))
        self.assertEqual(response['X-Vary-On-View'], 'False;')
        self.assertContains(response, 'test_authentication_status: AnonymousUser')
        self.assertTrue(response.has_header('Last-Modified'))
        last_modified = response['Last-Modified']
        self.assertTrue(response.has_header('ETag'))
        etag = response['ETag']

        # Test out the 304 Not Modified feature while we're here.
        response = self.client.get(url, HTTP_IF_MODIFIED_SINCE=last_modified)
        self.assertEqual(response.status_code, 304)
        response = self.client.get(url, HTTP_IF_NONE_MATCH=etag)
        self.assertEqual(response.status_code, 304)

        # Log in as a user, and try the same page. If we send a Last-Modified
        # header, it should not make a difference. This is because it has a
        # different vary_on_view value now that a user is authenticted.
        self.assertTrue(self.client.login(username='testuser1', password='test'))
        response = self.client.get(url, HTTP_IF_MODIFIED_SINCE=last_modified)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.has_header('Vary'))
        self.assertFalse(response.has_header('X-From-Cache'))
        self.assertTrue(response.has_header('X-Vary-On-View'))
        self.assertEqual(response['X-Vary-On-View'], 'True;')
        self.assertContains(response, 'test_authentication_status: testuser1')

        # Try again and it will come from the cache, unless the
        # settings are configured to only cache anonymous users.
        response = self.client.get(url)
        self.assertTrue(response.has_header('Vary'))
        self.assertTrue(response.has_header('X-Vary-On-View'))
        if settings.CACHE_MIDDLEWARE_ANONYMOUS_ONLY:
            self.assertFalse(response.has_header('X-From-Cache'))
        else:
            self.assertTrue(response.has_header('X-From-Cache'))
            self.assertTrue(response.has_header('Etag'))
            response = self.client.get(url, HTTP_IF_NONE_MATCH=response['Etag'])
            self.assertEqual(response.status_code, 304)

        # Log out and it will get the cached version for anonymous users again.
        self.client.logout()
        response = self.client.get(url)
        self.assertTrue(response.has_header('Vary'))
        self.assertTrue(response.has_header('X-From-Cache'))
        self.assertTrue(response.has_header('X-Vary-On-View'))
        self.assertEqual(response['X-Vary-On-View'], 'False;')
        self.assertContains(response, 'test_authentication_status: AnonymousUser')

        # Log in as user2 and we should see the cached version for user1.
        # This is intended for the test. Nobody in their right mind would put
        # user specific content in a view that is decorated with
        # @vary_on_authentication_status
        self.assertTrue(self.client.login(username='testuser2', password='test'))
        response = self.client.get(url)
        self.assertTrue(response.has_header('Vary'))
        self.assertTrue(response.has_header('X-Vary-On-View'))
        self.assertEqual(response['X-Vary-On-View'], 'True;')
        if settings.CACHE_MIDDLEWARE_ANONYMOUS_ONLY:
            # If settings are configured to only cache anonymous users, then
            # this response should not have actually come from the cache.
            self.assertFalse(response.has_header('X-From-Cache'))
            self.assertContains(response, 'test_authentication_status: testuser2')
        else:
            self.assertTrue(response.has_header('X-From-Cache'))
            self.assertContains(response, 'test_authentication_status: testuser1')

    def test_undecorated(self):

        # Use the current time to make a URL that won't have been cached before.
        url = '/test_undecorated/?time=%s' % time.time()

        # The first access will not be cached. The response should not have
        # any vary headers as it does not use any vary_on_view decorators,
        # and it does not rely on cookies (does not access the user).
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.has_header('Vary'))
        self.assertFalse(response.has_header('X-From-Cache'))
        self.assertFalse(response.has_header('X-Vary-On-View'))
        last_modified = response['Last-Modified']
        self.assertTrue(last_modified)
        etag = response['ETag']

        # This time, it should come from the cache.
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.has_header('Vary'))
        self.assertTrue(response.has_header('X-From-Cache'))

        # Check if etags result in a 304 Not Modified response.
        response = self.client.get(url, HTTP_IF_NONE_MATCH=etag)
        self.assertEqual(response.status_code, 304)

        # Log in as a user.
        User.objects.create_user(username='testuser1', email='', password='test')
        self.assertTrue(self.client.login(username='testuser1', password='test'))

        # 304 Not Modified should still work because the view doesn't vary.
        response = self.client.get(url, HTTP_IF_NONE_MATCH=etag)
        self.assertEqual(response.status_code, 304)

        # Normal requests should come out of the cache.
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.has_header('Vary'))
        self.assertTrue(response.has_header('X-From-Cache'))
        self.assertFalse(response.has_header('X-Vary-On-View'))

    def test_cache_page_decorator(self):
        """
        Django's decorator normally uses Django's middleware. It has been
        swapped with the custom middleware, so check that it works.

        """

        # Use the current time to make a URL that won't have been cached before.
        url = '/test_cache_page/?time=%s' % time.time()

        # Fetch the URL and it won't come from the cache. It should cache for
        # 60 days, as that is what is defined on the view.
        response = self.client.get(url)
        self.assertFalse(response.has_header('X-From-Cache'))
        self.assertTrue(response.has_header('Expires'))

        # It should be cached for 60 days. Because it takes a split second to
        # run, it ends up being 59.999999 days (which rounds down to 59). Just
        # to be extra safe, even though it's impossible, allow for either
        # 59 or 60 days difference.
        expires = parse_http_date(response['Expires'])
        today = datetime.datetime.now()
        days_different = (expires - today).days
        self.assertTrue(days_different in (59, 60))

        # Fetch it again and it should come from the cache.
        response = self.client.get(url)
        self.assertTrue(response.has_header('X-From-Cache'))

    def test_hack(self):
        """
        If this doesn't work, then the cache override has been overridden!
        This is a tricky thing to solve and it's hard to explain, but try to
        avoid importing django caching stuff in "low level" modules or modules
        that are imported by them.

        Look at django_cache_middleware.hack to see the override stuff.

        """

        from django.views.decorators.cache import CacheMiddleware
        self.assertEqual(CacheMiddleware.__module__, 'django_cache_middleware.middleware')
