import types

from pure_eval.utils import of_type, CannotEval

_sentinel = object()


def _static_getmro(klass):
    return type.__dict__['__mro__'].__get__(klass)


def _check_instance(obj, attr):
    instance_dict = {}
    try:
        instance_dict = object.__getattribute__(obj, "__dict__")
    except AttributeError:
        pass
    return dict.get(instance_dict, attr, _sentinel)


def _check_class(klass, attr):
    for entry in _static_getmro(klass):
        if _shadowed_dict(type(entry)) is _sentinel:
            try:
                return entry.__dict__[attr]
            except KeyError:
                pass
    return _sentinel


def _is_type(obj):
    try:
        _static_getmro(obj)
    except TypeError:
        return False
    return True


def _shadowed_dict(klass):
    dict_attr = type.__dict__["__dict__"]
    for entry in _static_getmro(klass):
        try:
            class_dict = dict_attr.__get__(entry)["__dict__"]
        except KeyError:
            pass
        else:
            if not (type(class_dict) is types.GetSetDescriptorType and
                    class_dict.__name__ == "__dict__" and
                    class_dict.__objclass__ is entry):
                return class_dict
    return _sentinel


def getattr_static(obj, attr):
    """Retrieve attributes without triggering dynamic lookup via the
       descriptor protocol,  __getattr__ or __getattribute__.

       Note: this function may not be able to retrieve all attributes
       that getattr can fetch (like dynamically created attributes)
       and may find attributes that getattr can't (like descriptors
       that raise AttributeError). It can also return descriptor objects
       instead of instance members in some cases. See the
       documentation for details.
    """
    instance_result = _sentinel
    if not _is_type(obj):
        klass = type(obj)
        dict_attr = _shadowed_dict(klass)
        if (dict_attr is _sentinel or
                type(dict_attr) is types.MemberDescriptorType):
            instance_result = _check_instance(obj, attr)
    else:
        klass = obj

    klass_result = _check_class(klass, attr)

    if instance_result is not _sentinel and klass_result is not _sentinel:
        if (_check_class(type(klass_result), '__get__') is not _sentinel and
                _check_class(type(klass_result), '__set__') is not _sentinel):
            return _resolve_descriptor(klass_result, obj)

    if instance_result is not _sentinel:
        return instance_result
    if klass_result is not _sentinel:
        get = _check_class(type(klass_result), '__get__')
        if get is _sentinel:
            return klass_result
        else:
            return _resolve_descriptor(klass_result, obj)

    if obj is klass:
        # for types we check the metaclass too
        for entry in _static_getmro(type(klass)):
            if _shadowed_dict(type(entry)) is _sentinel:
                try:
                    return entry.__dict__[attr]
                except KeyError:
                    pass
    raise CannotEval


class _foo:
    __slots__ = ['foo']


slot_descriptor = type(_foo.foo)
wrapper_descriptor = type(str.__dict__['__add__'])
method_descriptor = type(str.__dict__['startswith'])


def _resolve_descriptor(d, obj):
    return of_type(
        d,
        slot_descriptor,
        wrapper_descriptor,
        method_descriptor,
    ).__get__(obj)
