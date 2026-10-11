"""Tests du type checker : types inférés, annotations, erreurs attendues."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from compiler import driver
from compiler.driver import CompileErrors
from compiler.errors import AirNameError, AirTypeError


def errors_of(src: str):
    try:
        driver.check(src, "t.air")
    except CompileErrors as ce:
        return ce.errors
    return []


def first_error(src: str):
    errs = errors_of(src)
    assert errs, "une erreur était attendue"
    return errs[0]


def ok(src: str):
    assert errors_of(src) == []


# ── Programmes valides ────────────────────────────────────────────────────────

def test_inference_and_widening():
    ok("x = 1\ny: Float = x\nz = x + 2.5\n")

def test_return_type_inferred_before_definition():
    ok("print(double(2))\nfun double(n: Int)\n    return n * 2\nend\n")

def test_globals_visible_in_functions():
    ok("limit = 3\nfun f() -> Int\n    return limit\nend\n")

def test_default_and_named_arguments():
    ok('fun g(a: Int, b: Int = 2) -> Int\n    return a + b\nend\nx = g(b: 5, a: 1)\ny = g(1)\n')

def test_blueprint_defaults_and_methods():
    ok('blueprint P\n    n: String\n    a: Int = 1\n    fun up()\n        a = a + 1\n    end\nend\n'
       'p = P.new(n: "x")\np.up()\nprint(p.a)\n')

def test_nodes_are_annotated():
    from compiler.ast_nodes import Assign, BinaryOp
    prog = driver.check("x = 1 + 2\ny = x * 2.0\n", "t.air")
    assert str(prog.statements[0].value.ty) == "Int"
    assert str(prog.statements[1].value.ty) == "Float"
    assert prog.statements[0].declares is True


# ── Erreurs de type ───────────────────────────────────────────────────────────

def test_string_plus_int_is_error_with_interpolation_hint():
    e = first_error('x = "a" + 3\n')
    assert isinstance(e, AirTypeError)
    assert "String" in e.message and "Int" in e.message
    assert "interpolation" in e.hint

def test_unknown_variable_suggests_close_name():
    e = first_error("username = 1\nprint(usernam)\n")
    assert isinstance(e, AirNameError)
    assert "usernam" in e.message and "`username`" in e.hint

def test_unknown_function():
    e = first_error("foo(1)\n")
    assert "fonction inconnue" in e.message

def test_wrong_argument_count():
    assert "attend 1 argument" in first_error("fun f(a: Int)\n    print(a)\nend\nf(1, 2)\n").message

def test_missing_argument():
    assert "manquant" in first_error("fun f(a: Int, b: Int)\n    print(a)\nend\nf(1)\n").message

def test_argument_type_mismatch():
    assert "type incompatible" in first_error('fun f(a: Int)\n    print(a)\nend\nf("x")\n').message

def test_float_not_assignable_to_int():
    assert "type incompatible" in first_error("x: Int = 2.5\n").message

def test_condition_must_be_bool():
    assert "Bool" in first_error("x = 1\nif x\n    print(x)\nend\n").message

def test_const_cannot_be_reassigned():
    assert "constante" in first_error("const A = 1\nA = 2\n").message

def test_missing_return_detected():
    assert "return" in first_error("fun f(x: Int) -> Int\n    if x > 0\n        return 1\n    end\nend\n").message

def test_unknown_type_name():
    e = first_error("x: Strng = 1\n")
    assert "type inconnu" in e.message and "String" in e.hint

def test_unknown_field_and_method():
    base = 'blueprint P\n    name: String\n    fun hi()\n        print(name)\n    end\nend\n'
    assert "champ" in first_error(base + 'p = P.new(name: "a")\nprint(p.nam)\n').message
    assert "méthode" in first_error(base + 'p = P.new(name: "a")\np.hii()\n').message

def test_required_field_missing():
    assert "requis" in first_error('blueprint P\n    name: String\nend\np = P.new()\n').message

def test_return_outside_function():
    assert "en dehors" in first_error("return 1\n").message

def test_void_value_cannot_be_used():
    assert "ne produit pas de valeur" in first_error("fun f()\n    print(1)\nend\nx = f()\n").message

def test_trait_must_be_implemented():
    src = "trait T\n    fun run()\nend\nblueprint B implements T\n    x: Int\nend\n"
    assert "manquante" in first_error(src).message

def test_multiple_errors_are_all_reported():
    assert len(errors_of('a = "x" + 1\nb: Int = "y"\nc = nope\n')) == 3
