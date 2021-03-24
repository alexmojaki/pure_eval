import ast
import builtins
import operator
from collections import ChainMap
from contextlib import suppress
from types import FrameType
from typing import Any, Tuple, Iterable, List, Mapping, Dict, Union, Set

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

        if not isinstance(node, ast.expr):
            raise TypeError("node should be an ast.expr, not {!r}".format(type(node).__name__))

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

        with suppress(Exception):
            return ast.literal_eval(node)

        if isinstance(node, ast.Name):
            try:
                return self.names[node.id]
            except KeyError:
                raise CannotEval
        elif isinstance(node, ast.Attribute):
            value = self[node.value]
            attr = node.attr
            return getattr_static(value, attr)
        elif isinstance(node, ast.Subscript):
            return self._handle_subscript(node)
        elif isinstance(node, (ast.List, ast.Tuple, ast.Set, ast.Dict)):
            return self._handle_container(node)
        elif isinstance(node, ast.UnaryOp):
            return self._handle_unary(node)
        elif isinstance(node, ast.BinOp):
            return self._handle_binop(node)
        elif isinstance(node, ast.BoolOp):
            return self._handle_boolop(node)

        raise CannotEval

    def _handle_boolop(self, node):
        allowed_types = (
            int,
            float,
            complex,
            bool,
            str,
            bytes,
            range,
            list,
            tuple,
            dict,
            set,
            frozenset,
            type(None),
        )
        left = of_type(self[node.values[0]], *allowed_types)

        for right in node.values[1:]:
            # We need short circuiting so that the whole operation can be evaluated
            # even if the right operand can't
            if isinstance(node.op, ast.Or):
                left = left or of_type(self[right], *allowed_types)
            else:
                assert isinstance(node.op, ast.And)
                left = left and of_type(self[right], *allowed_types)
        return left

    def _handle_binop(self, node):
        op_type = type(node.op)
        op = {
            ast.Add: operator.add,
            ast.Sub: operator.sub,
            ast.Mult: operator.mul,
            ast.Div: operator.truediv,
            ast.FloorDiv: operator.floordiv,
            ast.Mod: operator.mod,
            ast.Pow: operator.pow,
            ast.LShift: operator.lshift,
            ast.RShift: operator.rshift,
            ast.BitOr: operator.or_,
            ast.BitXor: operator.xor,
            ast.BitAnd: operator.and_,
        }.get(op_type)
        if not op:
            raise CannotEval
        # TODO allow dict, set, frozenset, checking for safe hash and ==
        allowed_types = (int, float, complex, bool, str, bytes, range, list, tuple)
        left = of_type(self[node.left], *allowed_types)
        right = of_type(self[node.right], *allowed_types)
        if (
            type(left) in (str, bytes)
            and op_type == ast.Mod
            # TODO allow collections containing other types safe to format
            and type(right) not in (int, float, complex, bool, str, bytes, range)
        ):
            raise CannotEval
        try:
            return op(left, right)
        except Exception as e:
            raise CannotEval from e

    def _handle_unary(self, node: ast.UnaryOp):
        value = of_type(
            self[node.operand],
            int,
            float,
            complex,
            bool,
            str,
            list,
            dict,
            set,
            tuple,
            frozenset,
            bytes,
            range,
            type(None),
        )
        op_type = type(node.op)
        op = {
            ast.USub: operator.neg,
            ast.UAdd: operator.pos,
            ast.Not: operator.not_,
            ast.Invert: operator.invert,
        }[op_type]
        try:
            return op(value)
        except Exception as e:
            raise CannotEval from e

    def _handle_subscript(self, node):
        value = self[node.value]
        index = node.slice
        if isinstance(index, ast.Slice):
            index = slice(*[
                None if p is None else of_type(self[p], int, bool)
                for p in [index.lower, index.upper, index.step]
            ])
        elif isinstance(index, ast.ExtSlice):
            raise CannotEval
        else:
            if isinstance(index, ast.Index):
                index = index.value
            index = self[index]

        if is_any(type(value), list, tuple, str, bytes, bytearray):
            if isinstance(index, slice):
                for i in [index.start, index.stop, index.step]:
                    of_type(i, int, bool, type(None))
            else:
                of_type(index, int, bool)
        else:
            of_type(value, dict)
            if not (
                    safe_hash_key(index)

                    # Have to ensure that the dict only contains keys that
                    # can safely be compared via __eq__ to the index.
                    # Don't bother for massive dicts to not kill performance
                    and len(value) < 10000
                    and all(map(safe_hash_key, value))
            ):
                raise CannotEval

        try:
            return value[index]
        except (KeyError, IndexError):
            raise CannotEval

    def _handle_container(
            self,
            node: Union[ast.List, ast.Tuple, ast.Set, ast.Dict]
    ) -> Union[List, Tuple, Set, Dict]:
        """Handle container nodes, including List, Set, Tuple and Dict"""
        elts = [
            self[elt] for elt in (
                node.keys if isinstance(node, ast.Dict) else node.elts
            )
        ]
        if isinstance(node, ast.List):
            return elts
        if isinstance(node, ast.Tuple):
            return tuple(elts)

        # Set and Dict
        if not all(map(safe_hash_key, elts)):
            raise CannotEval

        if isinstance(node, ast.Set):
            return set(elts)

        return {
            elt: self[val]
            for elt, val in zip(elts, node.values)
        }

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
