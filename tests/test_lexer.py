"""
tests/test_lexer.py — Suite de tests pour le Lexer AirLang
Couvre : mots-clés, littéraux, opérateurs, commentaires, erreurs.
Lancer : python3 -m pytest tests/test_lexer.py -v
      ou : python3 tests/test_lexer.py
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "compiler"))

from lexer import Lexer, Token, TokenType, LexerError
import traceback


# ── Utilitaire ────────────────────────────────────────────────────────────────

def tokenize(src: str):
    """Tokenise et retourne la liste sans NEWLINE ni EOF."""
    tokens = Lexer(src).tokenize()
    return [t for t in tokens if t.type not in (TokenType.NEWLINE, TokenType.EOF)]

def types(src: str):
    """Retourne uniquement les types de tokens."""
    return [t.type for t in tokenize(src)]

def values(src: str):
    """Retourne uniquement les valeurs de tokens."""
    return [t.value for t in tokenize(src)]


# ── Tests mots-clés ───────────────────────────────────────────────────────────

def test_keywords_basic():
    src = "fun blueprint trait import export return if else end"
    expected = [
        TokenType.FUN, TokenType.BLUEPRINT, TokenType.TRAIT,
        TokenType.IMPORT, TokenType.EXPORT, TokenType.RETURN,
        TokenType.IF, TokenType.ELSE, TokenType.END,
    ]
    assert types(src) == expected, f"Échec mots-clés basiques : {types(src)}"

def test_keywords_control():
    src = "for while in match unless then const new try catch"
    expected = [
        TokenType.FOR, TokenType.WHILE, TokenType.IN,
        TokenType.MATCH, TokenType.UNLESS, TokenType.THEN,
        TokenType.CONST, TokenType.NEW, TokenType.TRY, TokenType.CATCH,
    ]
    assert types(src) == expected, f"Échec mots-clés contrôle : {types(src)}"

def test_keywords_logical():
    src = "and or not"
    assert types(src) == [TokenType.AND, TokenType.OR, TokenType.NOT]

def test_keyword_extends_implements():
    src = "extends implements as"
    assert types(src) == [TokenType.EXTENDS, TokenType.IMPLEMENTS, TokenType.AS]

def test_bool_literals():
    toks = tokenize("true false")
    assert toks[0].type  == TokenType.BOOL
    assert toks[0].value == "true"
    assert toks[1].type  == TokenType.BOOL
    assert toks[1].value == "false"

def test_null_literal():
    toks = tokenize("null")
    assert toks[0].type == TokenType.NULL

def test_ident_not_keyword():
    """Un identifiant qui ressemble à un mot-clé mais n'en est pas un."""
    toks = tokenize("function blueprint2 ending")
    assert all(t.type == TokenType.IDENT for t in toks)


# ── Tests littéraux ───────────────────────────────────────────────────────────

def test_integer_literal():
    toks = tokenize("42")
    assert toks[0].type  == TokenType.INT
    assert toks[0].value == "42"

def test_integer_zero():
    toks = tokenize("0")
    assert toks[0].type == TokenType.INT

def test_float_literal():
    toks = tokenize("3.14")
    assert toks[0].type  == TokenType.FLOAT
    assert toks[0].value == "3.14"

def test_float_no_leading_zero():
    toks = tokenize("0.5")
    assert toks[0].type == TokenType.FLOAT

def test_string_simple():
    toks = tokenize('"Bonjour"')
    assert toks[0].type  == TokenType.STRING
    assert toks[0].value == "Bonjour"

def test_string_empty():
    toks = tokenize('""')
    assert toks[0].type  == TokenType.STRING
    assert toks[0].value == ""

def test_string_with_spaces():
    toks = tokenize('"hello world"')
    assert toks[0].value == "hello world"

def test_string_escape_newline():
    toks = tokenize(r'"line1\nline2"')
    assert "\n" in toks[0].value

def test_string_escape_tab():
    toks = tokenize(r'"col1\tcol2"')
    assert "\t" in toks[0].value

def test_string_escape_quote():
    toks = tokenize(r'"say \"hello\""')
    assert '"' in toks[0].value

def test_multiple_literals():
    toks = tokenize('42 3.14 "AirLang" true null')
    assert [t.type for t in toks] == [
        TokenType.INT, TokenType.FLOAT, TokenType.STRING,
        TokenType.BOOL, TokenType.NULL,
    ]


# ── Tests opérateurs ──────────────────────────────────────────────────────────

def test_arithmetic_operators():
    toks = tokenize("+ - * / %")
    assert [t.type for t in toks] == [
        TokenType.PLUS, TokenType.MINUS, TokenType.STAR,
        TokenType.SLASH, TokenType.PERCENT,
    ]

def test_comparison_operators():
    toks = tokenize("== != < > <= >=")
    assert [t.type for t in toks] == [
        TokenType.EQ, TokenType.NEQ,
        TokenType.LT, TokenType.GT,
        TokenType.LTE, TokenType.GTE,
    ]

def test_assignment_operators():
    toks = tokenize("= += -= *= /=")
    assert [t.type for t in toks] == [
        TokenType.ASSIGN, TokenType.PLUS_EQ, TokenType.MINUS_EQ,
        TokenType.STAR_EQ, TokenType.SLASH_EQ,
    ]

def test_arrow_operators():
    toks = tokenize("-> =>")
    assert toks[0].type == TokenType.ARROW
    assert toks[1].type == TokenType.FAT_ARROW

def test_dot_and_dotdot():
    toks = tokenize(". ..")
    assert toks[0].type == TokenType.DOT
    assert toks[1].type == TokenType.DOTDOT

def test_question_mark():
    toks = tokenize("?")
    assert toks[0].type == TokenType.QUESTION

def test_colon():
    toks = tokenize(":")
    assert toks[0].type == TokenType.COLON

def test_comma():
    toks = tokenize(",")
    assert toks[0].type == TokenType.COMMA


# ── Tests groupement ──────────────────────────────────────────────────────────

def test_grouping_tokens():
    toks = tokenize("( ) [ ] { }")
    assert [t.type for t in toks] == [
        TokenType.LPAREN, TokenType.RPAREN,
        TokenType.LBRACKET, TokenType.RBRACKET,
        TokenType.LBRACE, TokenType.RBRACE,
    ]


# ── Tests commentaires ────────────────────────────────────────────────────────

def test_comment_ignored():
    toks = tokenize("# ceci est un commentaire")
    assert toks == []

def test_comment_inline():
    toks = tokenize("x = 42  # valeur de x")
    assert len(toks) == 3
    assert toks[0].type == TokenType.IDENT
    assert toks[1].type == TokenType.ASSIGN
    assert toks[2].type == TokenType.INT

def test_double_hash_comment():
    toks = tokenize("## Documentation\nx = 1")
    assert toks[0].type == TokenType.IDENT
    assert toks[0].value == "x"


# ── Tests positions ───────────────────────────────────────────────────────────

def test_line_numbers():
    src = "a\nb\nc"
    tokens = Lexer(src).tokenize()
    idents = [t for t in tokens if t.type == TokenType.IDENT]
    assert idents[0].line == 1
    assert idents[1].line == 2
    assert idents[2].line == 3

def test_column_numbers():
    src = "a = 42"
    toks = tokenize(src)
    assert toks[0].column == 1   # 'a'
    assert toks[1].column == 3   # '='
    assert toks[2].column == 5   # '42'


# ── Tests programmes complets ─────────────────────────────────────────────────

def test_function_declaration():
    src = 'fun greet(name: String) -> String\n    return "Bonjour"\nend'
    toks = tokenize(src)
    assert toks[0].type == TokenType.FUN
    assert toks[1].type == TokenType.IDENT and toks[1].value == "greet"
    assert toks[2].type == TokenType.LPAREN
    assert toks[-1].type == TokenType.END

def test_blueprint_declaration():
    src = """blueprint Person
    name: String
    age: Int
end"""
    toks = tokenize(src)
    assert toks[0].type  == TokenType.BLUEPRINT
    assert toks[1].value == "Person"

def test_for_range():
    src = "for i in 0..10"
    toks = tokenize(src)
    assert toks[0].type == TokenType.FOR
    assert toks[2].type == TokenType.IN
    assert toks[3].type == TokenType.INT and toks[3].value == "0"
    assert toks[4].type == TokenType.DOTDOT
    assert toks[5].type == TokenType.INT and toks[5].value == "10"

def test_method_call_chain():
    src = "user.name.upper()"
    toks = tokenize(src)
    assert toks[0].value == "user"
    assert toks[1].type  == TokenType.DOT
    assert toks[2].value == "name"
    assert toks[3].type  == TokenType.DOT
    assert toks[4].value == "upper"

def test_lambda():
    src = "double = fun(x: Int) => x * 2"
    toks = tokenize(src)
    fun_idx = next(i for i, t in enumerate(toks) if t.type == TokenType.FUN)
    arrow_idx = next(i for i, t in enumerate(toks) if t.type == TokenType.FAT_ARROW)
    assert fun_idx < arrow_idx

def test_type_annotation_optional():
    src = "data: String? = null"
    toks = tokenize(src)
    assert toks[0].value == "data"
    assert toks[1].type  == TokenType.COLON
    assert toks[2].value == "String"
    assert toks[3].type  == TokenType.QUESTION

def test_import_as():
    src = 'import net.http as http'
    toks = tokenize(src)
    assert toks[0].type == TokenType.IMPORT
    assert toks[-1].value == "http"

def test_constructor_call():
    src = 'alice = Person.new(name: "Alice", age: 25)'
    toks = tokenize(src)
    assert toks[0].value == "alice"
    assert toks[2].value == "Person"
    assert toks[3].type  == TokenType.DOT
    assert toks[4].type  == TokenType.NEW


# ── Tests erreurs ─────────────────────────────────────────────────────────────

def test_unclosed_string_raises():
    try:
        Lexer('"chaîne non fermée').tokenize()
        assert False, "Devrait lever une LexerError"
    except LexerError as e:
        assert "non fermée" in str(e) or "Chaîne" in str(e)

def test_unexpected_character_raises():
    try:
        Lexer("x = 42 @ 5").tokenize()
        assert False, "Devrait lever une LexerError"
    except LexerError as e:
        assert "@" in str(e) or "inattendu" in str(e).lower()


# ── Runner ────────────────────────────────────────────────────────────────────

def run_all_tests():
    tests = [
        (name, fn) for name, fn in globals().items()
        if name.startswith("test_") and callable(fn)
    ]
    passed = 0
    failed = 0
    errors = []

    print(f"\n── Tests Lexer AirLang ({len(tests)} tests) ──────────────────")
    for name, fn in tests:
        try:
            fn()
            print(f"  ✓  {name}")
            passed += 1
        except Exception as e:
            print(f"  ✘  {name}")
            errors.append((name, traceback.format_exc()))
            failed += 1

    print(f"\n── Résultat : {passed}/{len(tests)} réussis ──────────────────")
    if errors:
        print("\nDétail des échecs :")
        for name, tb in errors:
            print(f"\n  [{name}]")
            for line in tb.strip().splitlines()[-4:]:
                print(f"    {line}")
    else:
        print("  Tous les tests ont réussi ✓")

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
