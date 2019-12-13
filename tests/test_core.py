import ast
import inspect

from pure_eval import Evaluator


def check_eval(source, *expected_values, total=True):
    frame = inspect.currentframe().f_back
    evaluator = Evaluator.from_frame(frame)
    root = ast.parse(source)
    values = []
    for node, value in evaluator.find_expressions(root):
        expr = ast.Expression(body=node)
        ast.copy_location(expr, node)
        code = compile(expr, "<expr>", "eval")
        expected = eval(code, frame.f_globals, frame.f_locals)
        assert value == expected
        values.append(value)
        if total:
            assert value in expected_values

    for expected in expected_values:
        assert expected in values


def test_eval():
    x = 3
    check_eval(
        "(x, check_eval, len)",
        x, check_eval, len,
        # TODO tuple (x, check_eval, len),
    )
