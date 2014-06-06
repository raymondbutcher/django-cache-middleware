import inspect
import hashlib

from django.utils.encoding import force_unicode

from urllib import quote


class HashableTuple(tuple):

    def __new__(cls, *items):
        return tuple.__new__(cls, cls._create_sequence(items))

    @classmethod
    def _create_one(cls, item):
        if isinstance(item, cls):
            return item
        elif isinstance(item, (list, tuple, set)):
            return tuple(cls._create_sequence(*item))
        if isinstance(item, dict):
            return tuple((key, cls._create_one(value)) for (key, value) in sorted(item.items()))
        elif inspect.isclass(item) or inspect.isfunction(item) or inspect.ismethod(item):
            return item.__name__
        elif isinstance(item, (int, basestring)):
            return force_unicode(item)
        else:
            return item

    @classmethod
    def _create_sequence(cls, *items):
        for item in items:
            yield cls._create_one(item)

    @property
    def hash(self):
        return hashlib.sha256(repr(self)).hexdigest()


def _quotify_function(func):
    def inner(*args, **kwargs):
        func_result = func(*args, **kwargs)
        return '%s;' % quote(str(func_result))
    return inner


def _combine_functions(*funcs):
    def inner(*args, **kwargs):
        result = ''
        for func in funcs:
            result += func(*args, **kwargs)
        return result
    return inner
