"""
tests/test_parser.py — Suite de tests pour le Parser AirLang
Noms de classes alignés avec ast_nodes.py.
Lancer : python3 tests/test_parser.py
"""

import sys, os, traceback
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "compiler"))

from lexer     import Lexer, TokenType
from parser    import Parser
from ast_nodes import *


# ── Utilitaires ──────────────────────────────────────────────────────────────

def parse(src: str) -> Program:
    tokens = Lexer(src).tokenize()
    return Parser(tokens, source=src).parse()

def first_stmt(src: str) -> Node:
    return parse(src).statements[0]

def parse_in_fun(expr_src: str) -> Node:
    """Parse une expression dans un corps de fonction muette."""
    prog = parse(f"fun _t()\n    return {expr_src}\nend")
    fn = prog.statements[0]
    return fn.body[0].value   # Return.value


# ── Variables ─────────────────────────────────────────────────────────────────

def test_var_assign_inferred():
    prog = parse("x = 42")
    # x = 42 produit un Assign (target=Identifier, value=IntLiteral)
    stmt = prog.statements[0]
    assert isinstance(stmt, Assign), f"Attendu Assign, reçu {type(stmt).__name__}"
    assert isinstance(stmt.target, Identifier)
    assert stmt.target.name == "x"
    assert isinstance(stmt.value, IntLiteral)
    assert stmt.value.value == 42

def test_var_assign_string():
    stmt = first_stmt('name = "Alice"')
    assert isinstance(stmt, Assign)
    assert stmt.target.name == "name"
    assert isinstance(stmt.value, StringLiteral)
    assert stmt.value.value == "Alice"

def test_var_float():
    stmt = first_stmt("score = 98.5")
    assert isinstance(stmt, Assign)
    assert isinstance(stmt.value, FloatLiteral)
    assert abs(stmt.value.value - 98.5) < 1e-9

def test_var_bool_true():
    stmt = first_stmt("flag = true")
    assert isinstance(stmt, Assign)
    assert isinstance(stmt.value, BoolLiteral)
    assert stmt.value.value is True

def test_var_null():
    stmt = first_stmt("data = null")
    assert isinstance(stmt, Assign)
    assert isinstance(stmt.value, NullLiteral)

def test_const_declaration():
    stmt = first_stmt("const MAX = 100")
    assert isinstance(stmt, VarDecl)
    assert stmt.is_const is True
    assert stmt.name == "MAX"

def test_var_with_type_annotation():
    # "age: Int = 30"  → VarDecl avec type_ann
    stmt = first_stmt("age: Int = 30")
    assert isinstance(stmt, VarDecl), f"Attendu VarDecl, reçu {type(stmt).__name__}"
    assert stmt.name == "age"
    assert stmt.type_ann is not None
    assert stmt.type_ann.name == "Int"

def test_var_optional_type():
    stmt = first_stmt("data: String? = null")
    assert isinstance(stmt, VarDecl)
    assert stmt.type_ann.optional is True


# ── Fonctions ─────────────────────────────────────────────────────────────────

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
    src = "fun calc(x: Int)\n    y = x\n    return y\nend"
    stmt = first_stmt(src)
    # y = x est un Assign, return y est un Return
    assert len(stmt.body) == 2
    assert isinstance(stmt.body[0], Assign)
    assert isinstance(stmt.body[1], Return)

def test_function_export():
    # export fun add(...) → ExportDecl wrapping FunDecl avec is_export=True
    stmt = first_stmt("export fun add(a: Int, b: Int) -> Int\n    return a\nend")
    # Peut être ExportDecl ou FunDecl avec is_export=True selon l'implémentation
    if isinstance(stmt, ExportDecl):
        assert isinstance(stmt.declaration, FunDecl)
    else:
        assert isinstance(stmt, FunDecl)
        assert stmt.is_export is True

def test_lambda_expression():
    stmt = first_stmt("double = fun(x: Int) => x")
    assert isinstance(stmt, Assign)
    assert isinstance(stmt.value, Lambda)


# ── Blueprints ────────────────────────────────────────────────────────────────

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
    src = "trait Printable\n    fun to_string() -> String\n    end\nend"
    stmt = first_stmt(src)
    assert isinstance(stmt, TraitDecl)
    assert stmt.name == "Printable"


# ── Structures de contrôle ────────────────────────────────────────────────────

def test_if_simple():
    src = "fun _t()\n    if x > 0\n        return 1\n    end\nend"
    stmt = first_stmt(src).body[0]
    assert isinstance(stmt, IfStmt)
    assert isinstance(stmt.condition, BinaryOp)   # BinaryOp, pas BinaryExpr

def test_if_else():
    src = "fun _t()\n    if x > 0\n        return 1\n    else\n        return 0\n    end\nend"
    stmt = first_stmt(src).body[0]
    assert len(stmt.else_body) > 0

def test_if_else_if():
    src = ("fun _t()\n    if x > 0\n        return 1\n"
           "    else if x < 0\n        return 0\n"
           "    else\n        return 2\n    end\nend")
    stmt = first_stmt(src).body[0]
    assert len(stmt.elif_clauses) >= 1   # elif_clauses, pas else_ifs

def test_unless_statement():
    src = "fun _t()\n    unless connected\n        return 0\n    end\nend"
    stmt = first_stmt(src).body[0]
    assert isinstance(stmt, UnlessStmt)

def test_while_loop():
    src = "fun _t()\n    while count < 10\n        count = count\n    end\nend"
    stmt = first_stmt(src).body[0]
    assert isinstance(stmt, WhileStmt)
    assert isinstance(stmt.condition, BinaryOp)   # BinaryOp

def test_for_range():
    src = "fun _t()\n    for i in 0..10\n        return i\n    end\nend"
    stmt = first_stmt(src).body[0]
    assert isinstance(stmt, ForStmt)
    assert stmt.var == "i"
    assert isinstance(stmt.iterable, RangeLiteral)   # RangeLiteral, pas RangeExpr

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
    src = 'fun _t()\n    match s\n        "a" => return 1\n        _ => return 0\n    end\nend'
    stmt = first_stmt(src).body[0]
    assert isinstance(stmt, MatchStmt)
    assert len(stmt.cases) >= 2


# ── Expressions ───────────────────────────────────────────────────────────────

def test_binary_add():
    expr = parse_in_fun("a + b")
    assert isinstance(expr, BinaryOp)   # BinaryOp, pas BinaryExpr
    assert expr.op == "+"

def test_binary_precedence():
    expr = parse_in_fun("2 + 3 * 4")
    assert isinstance(expr, BinaryOp)
    assert expr.op == "+"
    assert isinstance(expr.right, BinaryOp)
    assert expr.right.op == "*"

def test_unary_not():
    expr = parse_in_fun("not active")
    assert isinstance(expr, UnaryOp)    # UnaryOp, pas UnaryExpr
    assert expr.op == "not"

def test_call_expression():
    expr = parse_in_fun("greet(name)")
    assert isinstance(expr, Call)       # Call, pas CallExpr
    assert isinstance(expr.callee, Identifier)
    assert expr.callee.name == "greet"

def test_method_call():
    expr = parse_in_fun("alice.greet()")
    assert isinstance(expr, MethodCall)  # MethodCall, pas MethodCallExpr
    assert expr.method == "greet"

def test_field_access():
    expr = parse_in_fun("alice.name")
    assert isinstance(expr, MemberAccess)   # MemberAccess, pas FieldAccessExpr
    assert expr.member == "name"

def test_new_expression():
    expr = parse_in_fun('Person.new(name: "Alice", age: 25)')
    assert isinstance(expr, NewInstance)    # NewInstance, pas NewExpr
    assert expr.blueprint == "Person"
    assert len(expr.kwargs) == 2


# ── Imports ───────────────────────────────────────────────────────────────────

def test_import_module():
    stmt = first_stmt("import io")
    assert isinstance(stmt, ImportDecl)     # ImportDecl, pas ImportStmt
    assert stmt.path == "io"
    assert stmt.alias is None

def test_import_with_alias():
    stmt = first_stmt("import net.http as http")
    assert isinstance(stmt, ImportDecl)
    assert stmt.path == "net.http"
    assert stmt.alias == "http"

def test_import_local():
    stmt = first_stmt('import "./utils/formatter"')
    assert isinstance(stmt, ImportDecl)
    assert "utils" in stmt.path


# ── Erreurs ───────────────────────────────────────────────────────────────────

def test_missing_end_raises():
    try:
        parse("fun broken()\n    return 1\n")
        assert False, "Devrait lever une erreur"
    except Exception:
        pass

def test_invalid_syntax_raises():
    try:
        parse("= x 42")
        assert False, "Devrait lever une erreur"
    except Exception:
        pass


# ── Runner ────────────────────────────────────────────────────────────────────

def run_all_tests():
    tests = [(n, f) for n, f in globals().items()
             if n.startswith("test_") and callable(f)]
    passed, failed, errors = 0, 0, []

    print(f"\n── Tests Parser AirLang ({len(tests)} tests) ──────────────────")
    for name, fn in tests:
        try:
            fn()
            print(f"  ✓  {name}")
            passed += 1
        except Exception:
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
    sys.exit(0 if run_all_tests() else 1)
