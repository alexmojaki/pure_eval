import ast
import enum
import sys
import typing


class CannotEval(Exception):
    def __repr__(self):
        return self.__class__.__name__

    __str__ = __repr__


def is_any(x, *args):
    return any(
        x is arg
        for arg in args
    )


def of_type(x, *types):
    if is_any(type(x), *types):
        return x
    else:
        raise CannotEval


def safe_hash_key(k):
    if is_any(type(k), str, int, bool, float, bytes, type, complex, range):
        return True
    if is_any(type(k), tuple, frozenset):
        return all(map(safe_hash_key, k))


class _E(enum.Enum):
    pass


class _C:
    def foo(self): pass  # pragma: nocover

    def bar(self): pass  # pragma: nocover

    @classmethod
    def cm(cls): pass  # pragma: nocover

    @staticmethod
    def sm(): pass  # pragma: nocover


safe_name_samples = {
    "len": len,
    "append": list.append,
    "__add__": list.__add__,
    "insert": [].insert,
    "__mul__": [].__mul__,
    "fromkeys": dict.__dict__['fromkeys'],
    "safe_hash_key": safe_hash_key,
    "__repr__": CannotEval.__repr__,
    "foo": _C().foo,
    "bar": _C.bar,
    "cm": _C.cm,
    "sm": _C.sm,
    "ast": ast,
    "CannotEval": CannotEval,
    "_E": _E,
}

typing_annotation_samples = {
    name: getattr(typing, name)
    for name in "List Dict Tuple Set Callable Mapping".split()
}

safe_name_types = tuple({
    type(f)
    for f in safe_name_samples.values()
})


typing_annotation_types = tuple({
    type(f)
    for f in typing_annotation_samples.values()
})


def eq_checking_types(a, b):
    return type(a) is type(b) and a == b


def ast_name(node):
    if isinstance(node, ast.Name):
        return node.id
    elif isinstance(node, ast.Attribute):
        return node.attr
    else:
        return None


def safe_name(value):
    typ = type(value)
    if is_any(typ, *safe_name_types):
        return value.__name__
    elif value is typing.Optional:
        return "Optional"
    elif value is typing.Union:
        return "Union"
    elif is_any(typ, *typing_annotation_types):
        return getattr(value, "__name__", None) or getattr(value, "_name", None)
    else:
        return None


def has_ast_name(value, node):
    value_name = safe_name(value)
    if type(value_name) is not str:
        return False
    return eq_checking_types(ast_name(node), value_name)


def copy_ast_without_context(x):
    if isinstance(x, ast.AST):
        kwargs = {
            field: copy_ast_without_context(getattr(x, field))
            for field in x._fields
            if field != 'ctx'
            if hasattr(x, field)
        }
        return type(x)(**kwargs)
    elif isinstance(x, list):
        return list(map(copy_ast_without_context, x))
    else:
        return x
