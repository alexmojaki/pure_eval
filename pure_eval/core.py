import ast
import builtins
from collections import ChainMap
from contextlib import suppress

from pure_eval.my_getattr_static import getattr_static
from pure_eval.utils import CannotEval, is_any, of_type, safe_hash_key, has_ast_name, copy_ast_without_context


class Evaluator:
    def __init__(self, names):
        self.names = names
        self._cache = {}

    @classmethod
    def from_frame(cls, frame):
        return cls(ChainMap(
            frame.f_locals,
            frame.f_globals,
            frame.f_builtins,
        ))

    def __getitem__(self, node):
        assert isinstance(node, ast.expr)
        with suppress(KeyError):
            result = self._cache[node]
            if result is CannotEval:
                raise CannotEval
            else:
                return result

        try:
            self._cache[node] = result = self.handle(node)
            return result
        except CannotEval:
            self._cache[node] = CannotEval
            raise

    def handle(self, node):
        with suppress(ValueError):
            return ast.literal_eval(node)

        if isinstance(node, ast.Name):
            try:
                return self.names[node.id]
            except KeyError:
                raise CannotEval

        if isinstance(node, ast.Attribute):
            value = self[node.value]
            attr = node.attr
            return getattr_static(value, attr)

        if isinstance(node, ast.Subscript):
            value = self[node.value]
            index = node.slice
            if is_any(type(value), list, tuple, str, bytes, bytearray):
                if isinstance(index, ast.Index):
                    key = of_type(self[index.value], int, bool)
                    try:
                        return value[key]
                    except IndexError:
                        raise CannotEval
                elif isinstance(index, ast.Slice):
                    return value[slice(*[
                        None if p is None else of_type(self[p], int, bool)
                        for p in [index.lower, index.upper, index.step]
                    ])]
            elif is_any(type(value), dict) and isinstance(index, ast.Index):
                key = self[index.value]
                if (
                        safe_hash_key(key)

                        # Have to ensure that the dict only contains keys that
                        # can safely be compared via __eq__ to the index.
                        # Don't bother for massive dicts to not kill performance
                        and len(value) < 10000
                        and all(map(safe_hash_key, value))
                ):
                    try:
                        return value[key]
                    except KeyError:
                        raise CannotEval

        raise CannotEval

    def find_expressions(self, root):
        for node in ast.walk(root):
            if not isinstance(node, ast.expr):
                continue

            try:
                value = self[node]
            except CannotEval:
                continue

            yield node, value

    def interesting_expressions_grouped(self, root):
        return group_expressions(
            pair
            for pair in self.find_expressions(root)
            if is_expression_interesting(*pair)
        )


def is_expression_interesting(node, value):
    with suppress(ValueError):
        ast.literal_eval(node)
        return False

    # TODO exclude inner modules, e.g. numpy.random.__name__ == 'numpy.random' != 'random'
    # TODO exclude common module abbreviations, e.g. numpy as np, pandas as pd
    if has_ast_name(value, node):
        return False

    if (
            isinstance(node, ast.Name)
            and getattr(builtins, node.id, object()) is value
    ):
        return False

    return True


def group_expressions(expressions):
    result = {}
    for node, value in expressions:
        dump = ast.dump(copy_ast_without_context(node))
        result.setdefault(dump, ([], value))[0].append(node)
    return result.values()
