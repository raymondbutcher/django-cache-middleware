Scenario
========

Problem
-------

A template shows one thing to all anonymous users, and something else to all
authenticated users (but nothing specific per-user, although that would be just
as easy to solve). There are 2 possible variations of content for this URL,
so the cache should have stored 2 responses for this URL.

In the template/view, there is a call to `request.user.is_authenticated()`
This will trigger the session backend to set `session.accessed = True`

When the session middleware sees this value, it will set `Vary: Cookie` on the
response headers. This is good because the user's browser needs to allow
a user to see version A, log in, see version B, log out, see version A, etc.
The browser has it's own caching and needs `Vary: Cookie` to work correctly.

When the built in Django cache middleware sees `Vary: Cookie`, it will cache a
response for each cookie value that is encountered. Each user has their own
"sessionid", which is included in the cookie value.

The cache middleware is now caching 1 version for every single unique session.
This could mean thousands of cached copies, but we only really needed two!


Solution
--------

There is no getting around the `Vary: Cookie` header that gets sent to the
client. This is needed for caching on their end. However, we can do the server
side caching more intelligently, so that only 2 responses will be stored.

Normally, after `request.user` is accessed, the cache middleware will use the
cookie value when generating a cache key for the response. This is a problem
because each user has their own cookie value. Instead of using the cookie
value in the cache key, this view can use the user's authentication status:
True or False.

The `vary_on_view` decorator will force the cache middleware to use a custom
value instead of the cookie value, while not affecting any response headers
that are needed by the client to correctly do its own caching.

You can decorate views with once-off functions, using lambdas or regularly
defined functions. They must take the same arguments as the view.

    @vary_on_view(lambda request, id: request.user.is_authenticated())
    def story_view(request, id):
        story = get_object_or_404(Story, id=id)
        authenticated = request.user.is_authenticated()
        data = {'story': story, 'authenticated': authenticated}
        return render_to_response('story.html', data)

You can also create reusable decorators for common usage. View the "decorators"
module to see the included ones, and to see how to make new ones. Here is the
same view, but using the included decorator `@vary_on_authentication_status`.

    @vary_on_authentication_status
    def story_view(request, id):
        story = get_object_or_404(Story, id=id)
        authenticated = request.user.is_authenticated()
        data = {'story': story, 'authenticated': authenticated}
        return render_to_response('story.html', data)
