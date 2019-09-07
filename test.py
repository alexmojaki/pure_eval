import asttokens

from pure_eval import Evaluator


class Foo:
    a = 1


foo = Foo()
foo.b = 2

ev = Evaluator(globals())
source = 'foo.__dict__["a"], [4, 5][foo.a]'
tokens = asttokens.ASTTokens(source, parse=True)
expressions = ev.find_expressions_with_text(tokens.tree, tokens.get_text)
for node, value in expressions.items():
    print(node, '=', repr(value))
