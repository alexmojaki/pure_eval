import ast


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


safe_name_samples = [
    len,
    list.append,
    list.__add__,
    [].append,
    [].__add__,
    dict.__dict__['fromkeys'],
    safe_hash_key,
    CannotEval.__repr__,
    CannotEval().__repr__,
    ast,
    CannotEval,
]

for f in safe_name_samples:
    assert isinstance(f.__name__, str)

safe_name_types = {
    type(f)
    for f in safe_name_samples
}


for f in safe_name_types:
    try:
        f.__name__ = lambda: 0
    except TypeError:
        pass
    else:
        assert False


def has_safe_name(x):
    return is_any(type(x), *safe_name_types)


def eq_checking_types(a, b):
    return type(a) is type(b) and a == b


def ast_name(node):
    if isinstance(node, ast.Name):
        return node.id
    elif isinstance(node, ast.Attribute):
        return node.attr
    else:
        return None


def has_ast_name(value, node):
    return has_safe_name(value) and eq_checking_types(value.__name__, ast_name(node))
