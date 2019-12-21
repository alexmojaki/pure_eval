# `pure_eval`

This is a Python package that lets you safely evaluate certain AST nodes without triggering arbitrary code that may have unwanted side effects.

For example, suppose we have an object defined as follows:

```python
class Rectangle:
    def __init__(self, width, height):
        self.width = width
        self.height = height

    @property
    def area(self):
        print("Calculating area...")
        return self.width * self.height


rect = Rectangle(3, 5)
```

Given the `rect` object, we want to evaluate whatever expressions we can in this source code:

```python
source = "(rect.width, rect.height, rect.area)"
```

This library works with the AST, so let's parse the source code and peek inside:

```python
import ast

tree = ast.parse(source)
the_tuple = tree.body[0].value
for node in the_tuple.elts:
    print(ast.dump(node))
```

Output:

```python
Attribute(value=Name(id='rect', ctx=Load()), attr='width', ctx=Load())
Attribute(value=Name(id='rect', ctx=Load()), attr='height', ctx=Load())
Attribute(value=Name(id='rect', ctx=Load()), attr='area', ctx=Load())
```

Now to actually use the library. First construct an Evaluator:

```python
from pure_eval import Evaluator

evaluator = Evaluator({"rect": rect})
```

The argument to `Evaluator` should be a mapping from variable names to their values. Or if you have access to the stack frame where `rect` is defined, you can instead use:

```python
evaluator = Evaluator.from_frame(frame)
```

Now to evaluate some nodes, using `evaluator[node]`:

```python
print("rect.width:", evaluator[the_tuple.elts[0]])
print("rect:", evaluator[the_tuple.elts[0].value])
```

Output:

```
rect.width: 3
rect: <__main__.Rectangle object at 0x105b0dd30>
```

OK, but you could have done the same thing with `eval`. The useful part is that it will refuse to evaluate the property `rect.area` because that would trigger unknown code. If we try, it'll raise a `CannotEval` exception.

```python
from pure_eval import CannotEval

try:
    print("rect.area:", evaluator[the_tuple.elts[2]])  # fails
except CannotEval as e:
    print(e)  # prints CannotEval
```

To find all the expressions that can be evaluated in a tree:

```python
for node, value in evaluator.find_expressions(tree):
    print(ast.dump(node), value)
```

Output:

```python
Attribute(value=Name(id='rect', ctx=Load()), attr='width', ctx=Load()) 3
Attribute(value=Name(id='rect', ctx=Load()), attr='height', ctx=Load()) 5
Name(id='rect', ctx=Load()) <__main__.Rectangle object at 0x105568d30>
Name(id='rect', ctx=Load()) <__main__.Rectangle object at 0x105568d30>
Name(id='rect', ctx=Load()) <__main__.Rectangle object at 0x105568d30>
```

Note that this includes `rect` three times, once for each appearance in the source code. Since all these nodes are equivalent, we can group them together:

```python
from pure_eval import group_expressions

for nodes, values in group_expressions(evaluator.find_expressions(tree)):
    print(len(nodes), "nodes with value:", values)
```

Output:

```
1 nodes with value: 3
1 nodes with value: 5
3 nodes with value: <__main__.Rectangle object at 0x10d374d30>
```

If we want to list all the expressions in a tree, we may want to filter out certain expressions whose values are obvious. For example, suppose we have a function `foo`:

```python
def foo():
    pass
```

If we refer to `foo` by its name as usual, then that's not interesting:

```python
from pure_eval import is_expression_interesting

node = ast.parse('foo').body[0].value
print(ast.dump(node))
print(is_expression_interesting(node, foo))
```

Output:

```python
Name(id='foo', ctx=Load())
False
```

But if we refer to it by a different name, then it's interesting:

```python
node = ast.parse('bar').body[0].value
print(ast.dump(node))
print(is_expression_interesting(node, foo))
```

Output:

```python
Name(id='bar', ctx=Load())
True
```

In general `is_expression_interesting` returns False for the following values:
- Literals (e.g. `123`, `'abc'`, `[1, 2, 3]`, `{'a': (), 'b': ([1, 2], [3])}`)
- Variables or attributes whose name is equal to the value's `__name__`, such as `foo` above or `self.foo` if it was a method.
- Builtins (e.g. `len`) referred to by their usual name.

To make things easier, you can combine finding expressions, grouping them, and filtering out the obvious ones with:

```python
evaluator.interesting_expressions_grouped(root)
```

To get the source code of an AST node, I recommend [asttokens](https://github.com/gristlabs/asttokens).

Here's a complete example that brings it all together:

```python
from asttokens import ASTTokens
from pure_eval import Evaluator

source = """
x = 1
d = {x: 2}
y = d[x]
"""

names = {}
exec(source, names)
atok = ASTTokens(source, parse=True)
for nodes, value in Evaluator(names).interesting_expressions_grouped(atok.tree):
    print(atok.get_text(nodes[0]), "=", value)
```

Output:

```python
x = 1
d = {1: 2}
y = 2
d[x] = 2
```
