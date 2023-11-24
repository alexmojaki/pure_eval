import sys
import unittest
import types

import pytest

from pure_eval import CannotEval
from pure_eval.my_getattr_static import getattr_static, safe_descriptors_raw


class TestGetattrStatic(unittest.TestCase):
    def assert_getattr(self, thing, attr):
        self.assertEqual(
            getattr_static(thing, attr),
            getattr(thing, attr),
        )

    def assert_cannot_getattr(self, thing, attr):
        with self.assertRaises(CannotEval):
            getattr_static(thing, attr)

    def test_basic(self):
        class Thing(object):
            x = object()

        thing = Thing()
        self.assert_getattr(thing, 'x')
        self.assert_cannot_getattr(thing, 'y')

    def test_inherited(self):
        class Thing(object):
            x = object()

        class OtherThing(Thing):
            pass

        something = OtherThing()
        self.assert_getattr(something, 'x')

    def test_instance_attr(self):
        class Thing(object):
            x = 2

            def __init__(self, x):
                self.x = x

        thing = Thing(3)
        self.assert_getattr(thing, 'x')
        self.assert_getattr(Thing, 'x')
        del thing.x
        self.assert_getattr(thing, 'x')

    def test_property(self):
        class Thing(object):
            @property
            def x(self):
                raise AttributeError("I'm pretending not to exist")

        thing = Thing()
        self.assert_cannot_getattr(thing, 'x')

        # TODO this should be doable as Thing.x is the property object
        # It would require checking that type(klass_result) is property and then just returning that
        self.assert_cannot_getattr(Thing, 'x')

    def test_descriptor_raises_AttributeError(self):
        class descriptor(object):
            def __get__(*_):
                raise AttributeError("I'm pretending not to exist")

        desc = descriptor()

        class Thing(object):
            x = desc

        thing = Thing()
        self.assert_cannot_getattr(thing, 'x')
        self.assert_cannot_getattr(Thing, 'x')

    def test_classAttribute(self):
        class Thing(object):
            x = object()

        self.assert_getattr(Thing, 'x')

    def test_classVirtualAttribute(self):
        class Thing(object):
            @types.DynamicClassAttribute
            def x(self):
                return self._x

            _x = object()

        self.assert_cannot_getattr(Thing(), 'x')
        self.assert_cannot_getattr(Thing, 'x')

    def test_inherited_classattribute(self):
        class Thing(object):
            x = object()

        class OtherThing(Thing):
            pass

        self.assert_getattr(OtherThing, 'x')

    def test_slots(self):
        class Thing(object):
            y = 'bar'
            __slots__ = ['x']

            def __init__(self):
                self.x = 'foo'

        thing = Thing()
        self.assert_getattr(thing, 'x')
        self.assert_getattr(Thing, 'x')
        self.assert_getattr(thing, 'y')
        self.assert_getattr(Thing, 'y')

        del thing.x
        self.assert_cannot_getattr(thing, 'x')

    def test_metaclass(self):
        class meta(type):
            attr = 'foo'

        class Thing(object, metaclass=meta):
            pass

        self.assert_getattr(Thing, 'attr')

        class SubThing(Thing):
            pass

        self.assert_getattr(SubThing, 'attr')

        class sub(meta):
            pass

        class OtherThing(object, metaclass=sub):
            x = 3

        self.assert_getattr(OtherThing, 'attr')

        class OtherOtherThing(OtherThing):
            pass

        self.assert_getattr(OtherOtherThing, 'x')
        self.assert_getattr(OtherOtherThing, 'attr')

    def test_no_dict_no_slots(self):
        self.assert_cannot_getattr(1, 'foo')
        self.assert_getattr('foo', 'lower')

    def test_no_dict_no_slots_instance_member(self):
        # returns descriptor
        with open(__file__) as handle:
            self.assert_cannot_getattr(handle, 'name')

    def test_inherited_slots(self):
        class Thing(object):
            __slots__ = ['x']

            def __init__(self):
                self.x = 'foo'

        class OtherThing(Thing):
            pass

        self.assert_getattr(OtherThing(), 'x')

    def test_descriptor(self):
        class descriptor(object):
            def __get__(self, instance, owner):
                return 3

        class Foo(object):
            d = descriptor()

        foo = Foo()

        # for a non data descriptor we return the instance attribute
        foo.__dict__['d'] = 1
        self.assert_getattr(foo, 'd')

        # if the descriptor is a data-descriptor it would be invoked so we can't get it
        descriptor.__set__ = lambda s, i, v: None
        self.assert_cannot_getattr(foo, 'd')

        del descriptor.__set__
        descriptor.__delete__ = lambda s, i, o: None
        self.assert_cannot_getattr(foo, 'd')

    def test_metaclass_with_descriptor(self):
        class descriptor(object):
            def __get__(self, instance, owner):
                return 3

        class meta(type):
            d = descriptor()

        class Thing(object, metaclass=meta):
            pass

        self.assert_cannot_getattr(Thing, 'd')

    def test_class_as_property(self):
        class Base(object):
            foo = 3

        class Something(Base):
            @property
            def __class__(self):
                return 1 / 0

        instance = Something()
        self.assert_getattr(instance, 'foo')
        self.assert_getattr(Something, 'foo')

    def test_mro_as_property(self):
        class Meta(type):
            @property
            def __mro__(self):
                return 1 / 0

        class Base(object):
            foo = 3

        class Something(Base, metaclass=Meta):
            pass

        self.assert_getattr(Something(), 'foo')
        self.assert_getattr(Something, 'foo')

    def test_dict_as_property(self):
        class Foo(dict):
            a = 3

            @property
            def __dict__(self):
                return 1 / 0

        foo = Foo()
        foo.a = 4
        self.assert_cannot_getattr(foo, 'a')
        self.assert_getattr(Foo, 'a')

    def test_custom_object_dict(self):
        class Custom(dict):
            def get(self, key, default=None):
                return 1 / 0

            __getitem__ = get

        class Foo(object):
            a = 3

        foo = Foo()
        foo.__dict__ = Custom()
        foo.x = 5
        self.assert_getattr(foo, 'a')
        self.assert_getattr(foo, 'x')

    def test_metaclass_dict_as_property(self):
        class Meta(type):
            @property
            def __dict__(self):
                return 1 / 0

        class Thing(metaclass=Meta):
            bar = 4

            def __init__(self):
                self.spam = 42

        instance = Thing()
        self.assert_getattr(instance, "spam")

        # TODO this fails with CannotEval, it doesn't like the __dict__ property,
        # but it seems that shouldn't actually matter because it's not called
        # self.assert_getattr(Thing, "bar")

    def test_module(self):
        self.assert_getattr(sys, "version")

    def test_metaclass_with_metaclass_with_dict_as_property(self):
        class MetaMeta(type):
            @property
            def __dict__(self):
                self.executed = True
                return dict(spam=42)

        class Meta(type, metaclass=MetaMeta):
            executed = False

        class Thing(metaclass=Meta):
            pass

        self.assert_cannot_getattr(Thing, "spam")
        self.assertFalse(Thing.executed)


def test_safe_descriptors_immutable():
    for d in safe_descriptors_raw:
        with pytest.raises((TypeError, AttributeError)):
            type(d).__get__ = None
