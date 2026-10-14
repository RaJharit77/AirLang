"""Tests « golden » : le rendu exact des messages d'erreur est une promesse de l'UX."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from compiler import driver
from compiler.driver import CompileErrors
from compiler.errors import LexerError, ParseError


def render(src: str, filename: str = "main.air") -> str:
    try:
        driver.check(src, filename)
    except CompileErrors as ce:
        return ce.errors[0].format(color=False)
    raise AssertionError("aucune erreur levée")


def test_golden_unknown_variable():
    src = "print(username)\n"
    assert render(src) == (
        "Erreur de nom : variable inconnue `username`\n"
        " --> main.air:1:7\n"
        "  |\n"
        "1 | print(username)\n"
        "  |       ^^^^^^^^\n"
        "  |\n"
        "  = aide : déclarez la variable avant de l'utiliser"
    )

def test_golden_type_mismatch_points_to_value():
    assert render('age: Int = "trente"\n') == (
        "Erreur de type : type incompatible : `Int` attendu, `String` reçu\n"
        " --> main.air:1:12\n"
        "  |\n"
        '1 | age: Int = "trente"\n'
        "  |            ^\n"
        "  |\n"
        "  = aide : fournissez une valeur de type `Int` ou corrigez l'annotation"
    )

def test_golden_string_plus_int_points_to_operator():
    out = render('x = 1\ny = "n=" + x\n')
    assert "main.air:2:10" in out   # le `+` est en colonne 10
    assert out.splitlines()[4].rstrip().endswith("^")

def test_golden_line_numbers_use_wide_gutter():
    src = "\n" * 11 + "print(oops)\n"
    out = render(src)
    assert " --> main.air:12:7" in out
    assert "12 | print(oops)" in out

def test_lexer_error_has_position_and_excerpt():
    try:
        driver.parse('x = 1 $ 2\n', "main.air")
    except LexerError as e:
        text = e.format()
        assert "caractère inattendu `$`" in text
        assert "main.air:1:7" in text and "x = 1 $ 2" in text
    else:
        raise AssertionError

def test_unterminated_string():
    try:
        driver.parse('x = "abc\n', "main.air")
    except LexerError as e:
        assert "non fermée" in e.message
    else:
        raise AssertionError

def test_missing_end_is_a_syntax_error():
    try:
        driver.parse("fun f()\n    print(1)\n", "main.air")
    except ParseError as e:
        assert "end" in e.format()
    else:
        raise AssertionError

def test_unsupported_feature_is_reported_not_miscompiled():
    try:
        driver.compile_to_c("x = Ok(1)\nprint(1)\n", "main.air")
    except CompileErrors as ce:
        assert "pas encore supporté" in ce.errors[0].message
        assert "v0.4" in ce.errors[0].hint
    else:
        raise AssertionError

def test_error_in_interpolation_points_inside_string():
    out = render('name = "a"\nprint("salut {nme}")\n')
    assert "variable inconnue `nme`" in out
    assert "main.air:2:15" in out


def test_decorator_is_a_clear_not_yet_supported_error():
    try:
        driver.parse("@native(\"x\")\nfun f()\nend\n", "main.air")
    except ParseError as e:
        assert "décorateurs" in e.message and "v0.5" in e.hint
        assert "main.air:1:1" in e.format()
    else:
        raise AssertionError
