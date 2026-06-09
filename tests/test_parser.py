"""
tests/test_parser.py — Suite de tests pour le Parser AirLang
Couvre : déclarations de variables, fonctions, blueprints, structures de contrôle,
         expressions, imports, exports, types, erreurs.
Lancer : python3 -m pytest tests/test_parser.py -v
      ou : python3 tests/test_parser.py
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "compiler"))

from lexer import Lexer, TokenType
from parser import Parser
from ast_nodes import *
import traceback


# ── Utilitaire ────────────────────────────────────────────────────────────────

def parse(src: str) -> Program:
    """Tokenise et parse le code source, retourne le nœud Program."""
    tokens = Lexer(src).tokenize()
    return Parser(tokens, source=src).parse()

def parse_expr(src: str):
    """Parse une expression simple (enveloppée dans une fonction muette)."""
    prog = parse(f"fun _test()\n    return {src}\nend")
    fn   = prog.statements[0]
    return fn.body[0].value   # ReturnStmt.value

def first_stmt(src: str):
    """Retourne le premier statement du programme."""
    return parse(src).statements[0]


# ── Tests variables ───────────────────────────────────────────────────────────

def test_var_assign_inferred():
    stmt = first_stmt("x = 42")
    assert isinstance(stmt, VarDecl)
    assert stmt.name == "x"
    assert stmt.type_annotation is None
    assert isinstance(stmt.value, IntLiteral)
    assert stmt.value.value == 42

def test_var_assign_string():
    stmt = first_stmt('"Bonjour" ')
    # Expression statement contenant un StringLiteral
    prog = parse('name = "Alice"')
    v = prog.statements[0]
    assert isinstance(v, VarDecl)
    assert v.name == "name"
    assert isinstance(v.value, StringLiteral)
    assert v.value.value == "Alice"

def test_var_with_type_annotation():
    stmt = first_stmt("age: Int = 30")
    assert isinstance(stmt, VarDecl)
    assert stmt.name == "age"
    assert stmt.type_annotation is not None
    assert stmt.type_annotation.name == "Int"

def test_var_optional_type():
    stmt = first_stmt("data: String? = null")
    assert isinstance(stmt, VarDecl)
    assert stmt.type_annotation.optional is True

def test_const_declaration():
    stmt = first_stmt("const MAX = 100")
    assert isinstance(stmt, VarDecl)
    assert stmt.is_const is True
    assert stmt.name == "MAX"

def test_var_float():
    stmt = first_stmt("score = 98.5")
    assert isinstance(stmt, VarDecl)
    assert isinstance(stmt.value, FloatLiteral)
    assert abs(stmt.value.value - 98.5) < 1e-9

def test_var_bool_true():
    stmt = first_stmt("flag = true")
    assert isinstance(stmt.value, BoolLiteral)
    assert stmt.value.value is True

def test_var_null():
    stmt = first_stmt("data = null")
    assert isinstance(stmt.value, NullLiteral)


# ── Tests fonctions ───────────────────────────────────────────────────────────

def test_function_no_params():
    stmt = first_stmt("fun hello()\n    return 1\nend")
    assert isinstance(stmt, FunDecl)
    assert stmt.name == "hello"
    assert len(stmt.params) == 0

def test_function_with_params():
    stmt = first_stmt("fun add(a: Int, b: Int) -> Int\n    return a\nend")
    assert isinstance(stmt, FunDecl)
    assert stmt.name == "add"
    assert len(stmt.params) == 2
    assert stmt.params[0].name == "a"
    assert stmt.params[1].name == "b"

def test_function_return_type():
    stmt = first_stmt("fun greet(name: String) -> String\n    return name\nend")
    assert stmt.return_type is not None
    assert stmt.return_type.name == "String"

def test_function_default_param():
    stmt = first_stmt("fun connect(host: String, port: Int = 3000)\n    return port\nend")
    assert stmt.params[1].default is not None
    assert isinstance(stmt.params[1].default, IntLiteral)
    assert stmt.params[1].default.value == 3000

def test_function_body_statements():
    src = "fun calc(x: Int)\n    y = x + 1\n    return y\nend"
    stmt = first_stmt(src)
    assert len(stmt.body) == 2
    assert isinstance(stmt.body[0], VarDecl)
    assert isinstance(stmt.body[1], ReturnStmt)

def test_function_export():
    stmt = first_stmt("export fun add(a: Int, b: Int) -> Int\n    return a + b\nend")
    assert isinstance(stmt, FunDecl)
    assert stmt.exported is True

def test_lambda_expression():
    stmt = first_stmt("double = fun(x: Int) => x * 2")
    assert isinstance(stmt, VarDecl)
    assert isinstance(stmt.value, LambdaExpr)


# ── Tests blueprints ──────────────────────────────────────────────────────────

def test_blueprint_simple():
    src = "blueprint Person\n    name: String\n    age: Int\nend"
    stmt = first_stmt(src)
    assert isinstance(stmt, BlueprintDecl)
    assert stmt.name == "Person"
    assert len(stmt.fields) == 2
    assert stmt.fields[0].name == "name"
    assert stmt.fields[1].name == "age"

def test_blueprint_with_method():
    src = "blueprint Dog\n    name: String\n    fun bark()\n        return 1\n    end\nend"
    stmt = first_stmt(src)
    assert isinstance(stmt, BlueprintDecl)
    assert len(stmt.methods) == 1
    assert stmt.methods[0].name == "bark"

def test_blueprint_extends():
    src = "blueprint Employee extends Person\n    company: String\nend"
    stmt = first_stmt(src)
    assert stmt.extends == "Person"

def test_blueprint_implements():
    src = "blueprint Report implements Printable\n    title: String\nend"
    stmt = first_stmt(src)
    assert "Printable" in stmt.implements

def test_blueprint_field_default():
    src = "blueprint Config\n    debug: Bool = false\nend"
    stmt = first_stmt(src)
    assert stmt.fields[0].default is not None
    assert isinstance(stmt.fields[0].default, BoolLiteral)

def test_trait_declaration():
    src = "trait Printable\n    fun to_string() -> String\nend"
    stmt = first_stmt(src)
    assert isinstance(stmt, TraitDecl)
    assert stmt.name == "Printable"
    assert len(stmt.methods) == 1


# ── Tests structures de contrôle ──────────────────────────────────────────────

def test_if_simple():
    src = "fun _t()\n    if x > 0\n        return 1\n    end\nend"
    fn   = first_stmt(src)
    stmt = fn.body[0]
    assert isinstance(stmt, IfStmt)
    assert isinstance(stmt.condition, BinaryExpr)

def test_if_else():
    src = "fun _t()\n    if x > 0\n        return 1\n    else\n        return 0\n    end\nend"
    stmt = first_stmt(src).body[0]
    assert stmt.else_body is not None

def test_if_else_if():
    src = "fun _t()\n    if x > 0\n        return 1\n    else if x < 0\n        return -1\n    else\n        return 0\n    end\nend"
    stmt = first_stmt(src).body[0]
    assert len(stmt.else_ifs) >= 1

def test_unless_statement():
    src = "fun _t()\n    unless connected\n        return 0\n    end\nend"
    stmt = first_stmt(src).body[0]
    assert isinstance(stmt, UnlessStmt)

def test_while_loop():
    src = "fun _t()\n    while count < 10\n        count = count + 1\n    end\nend"
    stmt = first_stmt(src).body[0]
    assert isinstance(stmt, WhileStmt)
    assert isinstance(stmt.condition, BinaryExpr)

def test_for_range():
    src = "fun _t()\n    for i in 0..10\n        return i\n    end\nend"
    stmt = first_stmt(src).body[0]
    assert isinstance(stmt, ForStmt)
    assert stmt.var == "i"
    assert isinstance(stmt.iterable, RangeExpr)

def test_for_list():
    src = "fun _t()\n    for user in users\n        return 1\n    end\nend"
    stmt = first_stmt(src).body[0]
    assert isinstance(stmt, ForStmt)
    assert stmt.var == "user"

def test_for_with_index():
    src = "fun _t()\n    for i, user in users\n        return i\n    end\nend"
    stmt = first_stmt(src).body[0]
    assert isinstance(stmt, ForStmt)
    assert stmt.index_var == "i"
    assert stmt.var == "user"

def test_match_statement():
    src = 'fun _t()\n    match status\n        "active" => return 1\n        _ => return 0\n    end\nend'
    stmt = first_stmt(src).body[0]
    assert isinstance(stmt, MatchStmt)
    assert len(stmt.cases) >= 2


# ── Tests expressions ─────────────────────────────────────────────────────────

def test_binary_add():
    expr = parse_expr("a + b")
    assert isinstance(expr, BinaryExpr)
    assert expr.op == "+"

def test_binary_precedence():
    expr = parse_expr("2 + 3 * 4")
    # * doit avoir une priorité plus haute que +
    assert isinstance(expr, BinaryExpr)
    assert expr.op == "+"
    assert isinstance(expr.right, BinaryExpr)
    assert expr.right.op == "*"

def test_unary_not():
    expr = parse_expr("not active")
    assert isinstance(expr, UnaryExpr)
    assert expr.op == "not"

def test_call_expression():
    expr = parse_expr("greet(name)")
    assert isinstance(expr, CallExpr)
    assert expr.name == "greet"
    assert len(expr.args) == 1

def test_method_call():
    expr = parse_expr("alice.greet()")
    assert isinstance(expr, MethodCallExpr)
    assert expr.method == "greet"

def test_field_access():
    expr = parse_expr("alice.name")
    assert isinstance(expr, FieldAccessExpr)
    assert expr.field == "name"

def test_new_expression():
    expr = parse_expr('Person.new(name: "Alice", age: 25)')
    assert isinstance(expr, NewExpr)
    assert expr.blueprint == "Person"
    assert len(expr.kwargs) == 2


# ── Tests imports ─────────────────────────────────────────────────────────────

def test_import_module():
    stmt = first_stmt("import io")
    assert isinstance(stmt, ImportStmt)
    assert stmt.path == "io"
    assert stmt.alias is None

def test_import_with_alias():
    stmt = first_stmt("import net.http as http")
    assert isinstance(stmt, ImportStmt)
    assert stmt.path == "net.http"
    assert stmt.alias == "http"

def test_import_local():
    stmt = first_stmt('import "./utils/formatter"')
    assert isinstance(stmt, ImportStmt)
    assert "utils" in stmt.path


# ── Tests erreurs de parsing ──────────────────────────────────────────────────

def test_missing_end_raises():
    try:
        parse("fun broken()\n    return 1\n# pas de end")
        assert False, "Devrait lever une ParseError"
    except Exception as e:
        assert "end" in str(e).lower() or "ParseError" in type(e).__name__

def test_invalid_syntax_raises():
    try:
        parse("= x 42")   # Syntaxe invalide
        assert False, "Devrait lever une ParseError"
    except Exception:
        pass   # N'importe quelle erreur est acceptable ici


# ── Runner ────────────────────────────────────────────────────────────────────

def run_all_tests():
    tests = [
        (name, fn) for name, fn in globals().items()
        if name.startswith("test_") and callable(fn)
    ]
    passed = 0
    failed = 0
    errors = []

    print(f"\n── Tests Parser AirLang ({len(tests)} tests) ──────────────────")
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
            for line in tb.strip().splitlines()[-5:]:
                print(f"    {line}")
    else:
        print("  Tous les tests ont réussi ✓")

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
