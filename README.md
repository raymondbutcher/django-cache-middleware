django-improved-cache-middleware
================================

Improved cache middleware for Django.

**Tested against Django 1.2.x**

What is improved?
-----------------

There are some aspects of Django's caching middleware that I felt could be
improved:
* It doesn't send `304 Not Modified` responses when there are appropriate
  cached response.
* When the `request.user` object is accessed, it varies the cache key based
  on the user's cookies. This results in separate cached responses for each
  individual user. It even caches responses individually for anonymous users!

Features
--------

* [Improved caching middleware](docs/features.md#cachemiddleware)
  * Returns "304 Not Modified" responses when it can, saving bandwidth and
    speeding up the user experience. Caches more situations effectively
    than Django's built-in middleware.
* [@vary_on_view decorator](docs/features.md#vary-on-view-decorator)
  * Provides specific control over view caching, without you having to write
    any caching code.
* [Strip cookies middleware](docs/features.md#strip-cookies-middleware)
  * Google Analytics stops the cache middleware from working correctly,
    and this middleware will solve that problem.

Scenario
--------

[A scenario that demonstrates the usefulness of
improved-django-caching](docs/scenario.md)
