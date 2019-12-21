import ast
import builtins
from collections import ChainMap
from contextlib import suppress
from types import FrameType
from typing import Any, Tuple, Iterable, List, Mapping, Dict

from pure_eval.my_getattr_static import getattr_static
from pure_eval.utils import CannotEval, is_any, of_type, safe_hash_key, has_ast_name, copy_ast_without_context


class Evaluator:
    def __init__(self, names: Mapping[str, Any]):
        """
        Construct a new evaluator with the given variable names.
        This is a low level API, typically you will use `Evaluator.from_frame(frame)`.

        :param names: a mapping from variable names to their values.
        """

        self.names = names
        self._cache = {}  # type: Dict[ast.expr, Any]

    @classmethod
    def from_frame(cls, frame: FrameType) -> 'Evaluator':
        """
        Construct an Evaluator that can look up variables from the given frame.

        :param frame: a frame object, e.g. from a traceback or `inspect.currentframe().f_back`.
        """

        return cls(ChainMap(
            frame.f_locals,
            frame.f_globals,
            frame.f_builtins,
        ))

    def __getitem__(self, node: ast.expr) -> Any:
        """
        Find the value of the given node.
        If it cannot be evaluated safely, this raises `CannotEval`.
        The result is cached either way.

        :param node: an AST expression to evaluate
        :return: the value of the node
        """

        assert isinstance(node, ast.expr)
        with suppress(KeyError):
            result = self._cache[node]
            if result is CannotEval:
                raise CannotEval
            else:
                return result

        try:
            self._cache[node] = result = self._handle(node)
            return result
        except CannotEval:
            self._cache[node] = CannotEval
            raise

    def _handle(self, node: ast.expr) -> Any:
        """
        This is where the evaluation happens.
        Users should use `__getitem__`, i.e. `evaluator[node]`,
        as it provides caching.

        :param node: an AST expression to evaluate
        :return: the value of the node
        """

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

    def find_expressions(self, root: ast.AST) -> Iterable[Tuple[ast.expr, Any]]:
        """
        Find all expressions in the given tree that can be safely evaluated.
        This is a low level API, typically you will use `interesting_expressions_grouped`.

        :param root: any AST node
        :return: generator of pairs (tuples) of expression nodes and their corresponding values.
        """

        for node in ast.walk(root):
            if not isinstance(node, ast.expr):
                continue

            try:
                value = self[node]
            except CannotEval:
                continue

            yield node, value

    def interesting_expressions_grouped(self, root: ast.AST) -> List[Tuple[List[ast.expr], Any]]:
        """
        Find all interesting expressions in the given tree that can be safely evaluated,
        grouping equivalent nodes together.

        For more control and details, see:
         - Evaluator.find_expressions
         - is_expression_interesting
         - group_expressions

        :param root: any AST node
        :return: A list of pairs (tuples) containing:
                    - A list of equivalent AST expressions
                    - The value of the first expression node
                       (which should be the same for all nodes, unless threads are involved)
        """

        return group_expressions(
            pair
            for pair in self.find_expressions(root)
            if is_expression_interesting(*pair)
        )


def is_expression_interesting(node: ast.expr, value: Any) -> bool:
    """
    Determines if an expression is potentially interesting, at least in my opinion.
    Returns False for the following expressions whose value is generally obvious:
        - Literals (e.g. 123, 'abc', [1, 2, 3], {'a': (), 'b': ([1, 2], [3])})
        - Variables or attributes whose name is equal to the value's __name__.
            For example, a function `def foo(): ...` is not interesting when referred to
            as `foo` as it usually would, but `bar` can be interesting if `bar is foo`.
            Similarly the method `self.foo` is not interesting.
        - Builtins (e.g. `len`) referred to by their usual name.

    This is a low level API, typically you will use `interesting_expressions_grouped`.

    :param node: an AST expression
    :param value: the value of the node
    :return: a boolean: True if the expression is interesting, False otherwise
    """

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


def group_expressions(expressions: Iterable[Tuple[ast.expr, Any]]) -> List[Tuple[List[ast.expr], Any]]:
    """
    Organise expression nodes and their values such that equivalent nodes are together.
    Two nodes are considered equivalent if they have the same structure,
    ignoring context (Load, Store, or Delete) and location (lineno, col_offset).
    For example, this will group together the same variable name mentioned multiple times in an expression.

    This will not check the values of the nodes. Equivalent nodes should have the same values,
    unless threads are involved.

    This is a low level API, typically you will use `interesting_expressions_grouped`.

    :param expressions: pairs of AST expressions and their values, as obtained from
                          `Evaluator.find_expressions`, or `(node, evaluator[node])`.
    :return: A list of pairs (tuples) containing:
                - A list of equivalent AST expressions
                - The value of the first expression node
                   (which should be the same for all nodes, unless threads are involved)
    """

    result = {}
    for node, value in expressions:
        dump = ast.dump(copy_ast_without_context(node))
        result.setdefault(dump, ([], value))[0].append(node)
    return list(result.values())
