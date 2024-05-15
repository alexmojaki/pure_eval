import ast
import inspect
import io
import os
import re
import sys
import typing
from itertools import islice

import pytest

from pure_eval import CannotEval
from pure_eval.utils import (
    copy_ast_without_context,
    safe_name_types,
    safe_name_samples,
    safe_name,
    typing_annotation_samples,
    is_standard_types,
    ensure_dict,
)


def sys_modules_sources():
    for module in sys.modules.values():
        try:
            filename = inspect.getsourcefile(module)
        except TypeError:
            continue

        if not filename:
            continue

        filename = os.path.abspath(filename)
        try:
            with io.open(filename) as f:
                source = f.read()
        except OSError:
            continue

        tree = ast.parse(source)
        yield filename, source, tree


def test_sys_modules():
    modules = sys_modules_sources()
    if not os.environ.get('PURE_EVAL_SLOW_TESTS'):
        modules = islice(modules, 0, 3)

    for filename, source, tree in modules:
        print(filename)
        if not filename.endswith("ast.py"):
            check_copy_ast_without_context(tree)


def check_copy_ast_without_context(tree):
    tree2 = copy_ast_without_context(tree)
    dump1 = ast.dump(tree)
    dump2 = ast.dump(tree2)
    normalised_dump1 = re.sub(
        # Two possible matches:
        # - first one like ", ctx=…" where ", " should be removed
        # - second one like "(ctx=…" where "(" should be kept
        (
            r"("
                r", ctx=(Load|Store|Del)\(\)"
            r"|"
                r"(?<=\()ctx=(Load|Store|Del)\(\)"
            r")"
        ),
        "",
        dump1
    )
    assert normalised_dump1 == dump2


def test_repr_cannot_eval():
    assert repr(CannotEval()) == "CannotEval"


def test_safe_name_types():
    for f in safe_name_types:
        with pytest.raises(TypeError):
            f.__name__ = lambda: 0


def test_safe_name_samples():
    for name, f in {**safe_name_samples, **typing_annotation_samples}.items():
        assert name == safe_name(f)


def test_safe_name_direct():
    assert safe_name(list) == "list"
    assert safe_name(typing.List) == "List"
    assert safe_name(typing.Union) == "Union"
    assert safe_name(typing.Optional) == "Optional"
    assert safe_name(3) is None


def test_is_standard_types():
    assert is_standard_types(0, check_dict_values=True, deep=True)
    assert is_standard_types("0", check_dict_values=True, deep=True)
    assert is_standard_types([0], check_dict_values=True, deep=True)
    assert is_standard_types({0}, check_dict_values=True, deep=True)
    assert is_standard_types({0: "0"}, check_dict_values=True, deep=True)
    assert not is_standard_types(is_standard_types, check_dict_values=True, deep=True)
    assert not is_standard_types([is_standard_types], check_dict_values=True, deep=True)
    assert is_standard_types([is_standard_types], check_dict_values=True, deep=False)
    assert is_standard_types({is_standard_types}, check_dict_values=True, deep=False)
    assert is_standard_types(
        {is_standard_types: is_standard_types}, check_dict_values=True, deep=False
    )
    assert not is_standard_types(
        {is_standard_types: is_standard_types}, check_dict_values=True, deep=True
    )
    assert not is_standard_types(
        {0: is_standard_types}, check_dict_values=True, deep=True
    )
    assert is_standard_types({0: is_standard_types}, check_dict_values=False, deep=True)
    assert is_standard_types([[[[[[[{(0,)}]]]]]]], deep=True, check_dict_values=True)
    assert not is_standard_types(
        [[[[[[[{(is_standard_types,)}]]]]]]], deep=True, check_dict_values=True
    )

    lst = []
    lst.append(lst)
    assert is_standard_types(lst, deep=False, check_dict_values=True)
    assert not is_standard_types(lst, deep=True, check_dict_values=True)

    lst = [0] * 1000000
    assert is_standard_types(lst, deep=False, check_dict_values=True)
    assert is_standard_types(lst[0], deep=True, check_dict_values=True)
    assert not is_standard_types(lst, deep=True, check_dict_values=True)

    lst = [[0] * 1000] * 1000
    assert is_standard_types(lst, deep=False, check_dict_values=True)
    assert is_standard_types(lst[0], deep=True, check_dict_values=True)
    assert not is_standard_types(lst, deep=True, check_dict_values=True)


def test_ensure_dict():
    assert ensure_dict({}) == {}
    assert ensure_dict([]) == {}
    assert ensure_dict('foo') == {}
    assert ensure_dict({'a': 1}) == {'a': 1}
