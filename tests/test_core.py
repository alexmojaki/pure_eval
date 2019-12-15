import ast
import inspect

from pure_eval import Evaluator
from pure_eval.core import is_expression_interesting, group_expressions


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


def test_eval_names():
    x = 3
    check_eval(
        "(x, check_eval, len), nonexistent",
        x, check_eval, len,
        # TODO tuple (x, check_eval, len),
    )


def test_eval_literals():
    check_eval(
        "(1, 'a', [{}])",
        (1, 'a', [{}]),
        1, 'a', [{}],
        {},
    )


def test_eval_attrs():
    class Foo:
        bar = 9

        @property
        def prop(self):
            return 0

        def method(self):
            pass

    foo = Foo()
    foo.spam = 44

    check_eval(
        "foo.bar + foo.spam + Foo.bar",
        foo.bar, foo.spam, Foo.bar, foo, Foo
    )

    check_eval(
        "Foo.spam + Foo.prop + foo.prop + foo.method() + Foo.method",
        foo, Foo, Foo.method, foo.method, 
    )


def test_eval_dict():
    d = {1: 2}

    # All is well, d[1] is evaluated
    check_eval(
        "d[1]",
        d[1], d, 1
    )

    class BadHash:
        def __hash__(self):
            return 0

    d[BadHash()] = 3

    # d[1] is not evaluated because d contains a bad key
    check_eval(
        "d[1]",
        d, 1
    )

    d = {1: 2}
    b = BadHash()

    # d[b] is not evaluated because b is a bad key
    check_eval(
        "d[b]",
        d, b
    )

    def make_d():
        return {1: 2}

    str(make_d())

    # Cannot eval make_d()[1] because the left part cannot eval
    check_eval(
        "make_d()[1]",
        make_d, 1
    )

    # Cannot eval d[:1] because slices aren't hashable
    check_eval(
        "d[:1]",
        d, 1
    )

    d = {(1, 3): 2}
    b = BadHash()

    # d[(1, b)] is not evaluated because b is a bad key
    check_eval(
        "d[(1, b)], d[(1, 3)]",
        d, b, d[(1, 3)], (1, 3), 1, 3
    )


def test_eval_sequence_subscript():
    lst = [12, 34, 56]
    i = 1
    check_eval(
        "lst[i] + lst[:i][0] + lst[i:][i] + lst[::2][False]",
        lst[i], lst[:i][0], lst[i:][i], lst[::2],
        lst, i, lst[:i], 0, lst[i:], 2,
    )

    check_eval(
        "('abc', 'def')[1][2]",
        ('abc', 'def')[1][2],
        total=False
    )


def check_interesting(source):
    frame = inspect.currentframe().f_back
    evaluator = Evaluator.from_frame(frame)
    root = ast.parse(source)
    node = root.body[0].value
    value = evaluator[node]

    expr = ast.Expression(body=node)
    ast.copy_location(expr, node)
    code = compile(expr, "<expr>", "eval")
    expected = eval(code, frame.f_globals, frame.f_locals)
    assert value == expected

    return is_expression_interesting(node, value)


def test_is_expression_interesting():
    class Foo:
        def method(self):
            pass

        alias = method

    foo = Foo()
    x = 1
    foo.x = x
    assert check_interesting('x')
    assert not check_interesting('help')
    assert not check_interesting('check_interesting')
    assert not check_interesting('[1]')
    assert check_interesting('[1, 2][0]')
    assert check_interesting('foo')
    assert not check_interesting('Foo')
    assert check_interesting('foo.x')
    assert not check_interesting('foo.method')
    assert check_interesting('foo.alias')
    assert not check_interesting('Foo.method')
    assert check_interesting('Foo.alias')


def test_group_expressions():
    x = (1, 2)
    evaluator = Evaluator({'x': x})
    tree = ast.parse('x[0] + x[x[0]]').body[0].value
    expressions = evaluator.find_expressions(tree)
    grouped = set(
        (frozenset(nodes), value)
        for nodes, value in
        group_expressions(expressions)
    )
    expected = {
        (frozenset([tree.left, tree.right.slice.value]),
         x[0]),
        (frozenset([tree.left.value, tree.right.slice.value.value, tree.right.value]),
         x),
        (frozenset([tree.left.slice.value, tree.right.slice.value.slice.value]),
         0),
        (frozenset([tree.right]),
         x[x[0]]),
    }
    assert grouped == expected

    grouped = set(
        (frozenset(nodes), value)
        for nodes, value in
        evaluator.interesting_expressions_grouped(tree)
    )
    expected = set(
        (nodes, value)
        for nodes, value in expected
        if value != 0
    )
    assert grouped == expected
