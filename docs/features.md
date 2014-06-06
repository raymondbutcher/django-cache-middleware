Features
========

CacheMiddleware
---------------

This middleware works slightly differently to Django's built-in options for
handling `304 Not Modified` responses. Here are some issues that I have found
with them:
 * `settings.USE_ETAGS` does not check `Last-Modified` headers.
 * `ConditionalGetMiddleware` can return incorrect `304 Not Modified`
   responses when the `Last-Modified` header matches, but the `Etag` does not.
 * Conditional View Processing doesn't do caching nor get used by the caching
   middleware.

This custom middleware:
 * Gets the `Etag`/`Last-Modified` headers out of the cached response in the
  `FetchFromCacheMiddleware` process_request phase. It then compares the
   headers to the request headers, and returns a `304 Not Modified` response
   if suitable. It does not have the issues mentioned above.

Additionally, this middleware works with the `@vary_on_view` decorator,
included in this library, to allow specific per-view caching rules.


@vary_on_view decorator
-------------------------

The `@vary_on_view` decorator allows you to fine-tune the caching of individual
views, while still using the cache middleware.

For example, you might want to cache your page based on the user's status. If
they are logged in, they see *A*, otherwise they see *B*. You cannot really do
this using the built-in Django middleware because it will cache a different
response for each user. The reasons for this are explained in the
[Scenario](scenario.md) document.

By using `@vary_on_view`, you can have view-specific caching rules that work
in synergy with the middleware. This works by removing the cookie value from
the cache key, and instead using the dynamic value created by the
`@vary_on_view` decorator.

Strip cookies middleware
------------------------

**Avoid using this if you can strip cookies before the request is given to
Django. Caching servers such as Varnish can strip cookies.**

Some cookies can destroy the ability to effectively cache a site. This
middleware strips them out before they interfere.

Google Analytics adds cookies that change on every single request. These are
generally only accessed by its own JavaScript code. They must be stripped out
before the caching middleware sees them.
