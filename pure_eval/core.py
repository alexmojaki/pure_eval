import ast
import builtins
from collections import ChainMap

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
        try:
            result = self._cache[node]
            if result is CannotEval:
                raise CannotEval
        except KeyError:
            pass

        try:
            self._cache[node] = result = self.handle(node)
            return result
        except CannotEval:
            self._cache[node] = CannotEval
            raise

    def handle(self, node):
        try:
            return ast.literal_eval(node)
        except ValueError:
            pass

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
                    return value[of_type(self[index.value], int, bool)]
                elif isinstance(index, ast.Slice):
                    return value[slice(*[
                        of_type(self[p], int, type(None), bool)
                        for p in [index.lower, index.upper, index.step]
                    ])]
            elif is_any(type(value), dict):
                if (
                        isinstance(index, ast.Index)
                        and safe_hash_key(self[index.value])

                        # Have to ensure that the dict only contains keys that
                        # can safely be compared via __eq__ to the index.
                        # Don't bother for massive dicts to not kill performance
                        and len(value) < 10000
                        and all(map(safe_hash_key, value))
                ):
                    return value[self[index.value]]

        raise CannotEval

    def find_expressions(self, root):
        for node in ast.walk(root):
            if not isinstance(node, ast.expr):
                continue

            try:
                ast.literal_eval(node)
                continue
            except ValueError:
                pass

            try:
                value = self[node]
            except CannotEval:
                continue

            # TODO exclude inner modules, e.g. numpy.random.__name__ == 'numpy.random' != 'random'
            # TODO exclude common module abbreviations, e.g. numpy as np, pandas as pd
            if has_ast_name(value, node):
                continue

            if (
                    isinstance(node, ast.Name)
                    and getattr(builtins, node.id, object()) is value
            ):
                continue

            yield node, value

    def find_expressions_grouped(self, root):
        result = {}
        for node, value in self.find_expressions(root):
            dump = ast.dump(copy_ast_without_context(node))
            result.setdefault(dump, ([], value))[0].append(node)
        return result.values()
