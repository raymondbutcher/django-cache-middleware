from django.utils.cache import add_never_cache_headers, get_max_age


class AdminCacheBypassMiddleware(object):

    def process_response(self, request, response):
        if request.path.startswith('/admin/'):
            if get_max_age(response) is None:
                add_never_cache_headers(response)
        return response
