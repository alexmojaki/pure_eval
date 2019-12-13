import ast
import io
import os
import re
import sys

from pure_eval.utils import copy_ast_without_context
import inspect


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
    modules = list(sys_modules_sources())
    if not os.environ.get('PURE_EVAL_SLOW_TESTS'):
        modules = modules[:20]

    for filename, source, tree in modules:
        print(filename)
        if not filename.endswith("ast.py"):
            check_copy_ast_without_context(tree)


def check_copy_ast_without_context(tree):
    tree2 = copy_ast_without_context(tree)
    dump1 = ast.dump(tree)
    dump2 = ast.dump(tree2)
    normalised_dump1 = re.sub(
        r", ctx=(Load|Store|Del)\(\)",
        "",
        dump1
    )
    assert normalised_dump1 == dump2
