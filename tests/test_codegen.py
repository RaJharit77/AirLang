"""
tests/test_codegen.py — Suite de tests pour le Générateur de Code C AirLang
Couvre : déclarations de variables, fonctions, blueprints, structures de contrôle,
         opérateurs, chaînes, listes, appels, retours, compilation end-to-end.
Lancer : python3 -m pytest tests/test_codegen.py -v
      ou : python3 tests/test_codegen.py
"""

import sys
import os
import subprocess
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "compiler"))

from lexer        import Lexer
from parser       import Parser
from type_checker import TypeChecker
from codegen_c    import CCodegen
import traceback


# ── Utilitaires ───────────────────────────────────────────────────────────────

RUNTIME_DIR = os.path.join(os.path.dirname(__file__), "..", "runtime")

def compile_to_c(src: str) -> str:
    """Compile du code AirLang en code C (sans exécuter)."""
    tokens  = Lexer(src).tokenize()
    ast     = Parser(tokens, source=src).parse()
    checker = TypeChecker()
    checker.check(ast)
    gen     = CCodegen()
    return gen.generate(ast)

def compile_and_run(src: str, stdin_input: str = "") -> tuple[str, int]:
    """
    Compile du code AirLang en C, compile avec GCC et exécute.
    Retourne (stdout, returncode).
    Nécessite GCC installé — les tests sont ignorés sinon.
    """
    c_code = compile_to_c(src)
    with tempfile.TemporaryDirectory() as tmpdir:
        c_file  = os.path.join(tmpdir, "prog.c")
        exe     = os.path.join(tmpdir, "prog")
        runtime_h = os.path.join(RUNTIME_DIR, "air_runtime.h")
        runtime_c = os.path.join(RUNTIME_DIR, "air_runtime.c")
        stdlib_c  = os.path.join(RUNTIME_DIR, "air_stdlib.c")

        with open(c_file, "w") as f:
            f.write(c_code)

        sources = [c_file, runtime_c]
        if os.path.exists(stdlib_c):
            sources.append(stdlib_c)

        result = subprocess.run(
            ["gcc", "-o", exe, "-I", RUNTIME_DIR, "-lm"] + sources,
            capture_output=True, text=True
        )
        if result.returncode != 0:
            raise RuntimeError(f"Erreur GCC :\n{result.stderr}")

        run_result = subprocess.run(
            [exe], input=stdin_input, capture_output=True,
            text=True, timeout=5
        )
        return run_result.stdout.strip(), run_result.returncode

def has_gcc() -> bool:
    """Vérifie si GCC est disponible."""
    try:
        subprocess.run(["gcc", "--version"], capture_output=True, timeout=3)
        return True
    except Exception:
        return False

GCC_AVAILABLE = has_gcc()


# ── Tests génération C (structure) ────────────────────────────────────────────

def test_codegen_produces_string():
    c = compile_to_c('x = 42')
    assert isinstance(c, str)
    assert len(c) > 0

def test_codegen_includes_runtime():
    c = compile_to_c('x = 1')
    assert "#include" in c
    assert "air_runtime" in c

def test_codegen_int_variable():
    c = compile_to_c('x = 42')
    assert "42" in c

def test_codegen_string_variable():
    c = compile_to_c('name = "Alice"')
    assert "Alice" in c

def test_codegen_float_variable():
    c = compile_to_c('score = 3.14')
    assert "3.14" in c

def test_codegen_bool_true():
    c = compile_to_c('flag = true')
    assert "true" in c or "1" in c

def test_codegen_function_declaration():
    src = "fun add(a: Int, b: Int) -> Int\n    return a + b\nend"
    c = compile_to_c(src)
    assert "add" in c
    assert "return" in c

def test_codegen_blueprint_struct():
    src = "blueprint Point\n    x: Float\n    y: Float\nend"
    c = compile_to_c(src)
    assert "Point" in c
    # Blueprint doit générer une struct ou équivalent
    assert "struct" in c or "typedef" in c

def test_codegen_if_statement():
    src = "fun _t()\n    if x > 0\n        return 1\n    end\nend"
    c = compile_to_c(src)
    assert "if" in c

def test_codegen_while_loop():
    src = "fun _t()\n    while count < 10\n        count = count + 1\n    end\nend"
    c = compile_to_c(src)
    assert "while" in c

def test_codegen_for_range():
    src = "fun _t()\n    for i in 0..10\n        return i\n    end\nend"
    c = compile_to_c(src)
    assert "for" in c

def test_codegen_binary_ops():
    for op in ["+", "-", "*", "/", "%"]:
        src = f"fun _t(a: Int, b: Int)\n    return a {op} b\nend"
        c = compile_to_c(src)
        assert op in c, f"Opérateur {op} absent du code généré"

def test_codegen_main_function():
    src = "fun main()\n    return 0\nend\nmain()"
    c = compile_to_c(src)
    assert "main" in c


# ── Tests compilation + exécution (nécessite GCC) ────────────────────────────

def test_e2e_hello_world():
    if not GCC_AVAILABLE:
        print("  (ignoré : GCC non disponible)")
        return
    src = 'fun main()\n    print("Bonjour AirLang")\nend\nmain()'
    out, code = compile_and_run(src)
    assert code == 0
    assert "Bonjour AirLang" in out

def test_e2e_integer_arithmetic():
    if not GCC_AVAILABLE:
        print("  (ignoré : GCC non disponible)")
        return
    src = 'fun main()\n    x = 6 * 7\n    print(x)\nend\nmain()'
    out, code = compile_and_run(src)
    assert code == 0
    assert "42" in out

def test_e2e_if_true_branch():
    if not GCC_AVAILABLE:
        print("  (ignoré : GCC non disponible)")
        return
    src = 'fun main()\n    if 10 > 5\n        print("vrai")\n    end\nend\nmain()'
    out, code = compile_and_run(src)
    assert "vrai" in out

def test_e2e_if_else():
    if not GCC_AVAILABLE:
        print("  (ignoré : GCC non disponible)")
        return
    src = ('fun main()\n'
           '    x = 3\n'
           '    if x > 5\n'
           '        print("grand")\n'
           '    else\n'
           '        print("petit")\n'
           '    end\n'
           'end\nmain()')
    out, code = compile_and_run(src)
    assert "petit" in out

def test_e2e_for_range():
    if not GCC_AVAILABLE:
        print("  (ignoré : GCC non disponible)")
        return
    src = ('fun main()\n'
           '    total = 0\n'
           '    for i in 1..5\n'
           '        total = total + i\n'
           '    end\n'
           '    print(total)\n'
           'end\nmain()')
    out, code = compile_and_run(src)
    assert "10" in out   # 1+2+3+4 = 10 (0..5 exclusif)

def test_e2e_function_call():
    if not GCC_AVAILABLE:
        print("  (ignoré : GCC non disponible)")
        return
    src = ('fun double(n: Int) -> Int\n'
           '    return n * 2\n'
           'end\n'
           'fun main()\n'
           '    result = double(21)\n'
           '    print(result)\n'
           'end\nmain()')
    out, code = compile_and_run(src)
    assert "42" in out

def test_e2e_while_countdown():
    if not GCC_AVAILABLE:
        print("  (ignoré : GCC non disponible)")
        return
    src = ('fun main()\n'
           '    n = 3\n'
           '    while n > 0\n'
           '        print(n)\n'
           '        n = n - 1\n'
           '    end\n'
           'end\nmain()')
    out, code = compile_and_run(src)
    assert "3" in out
    assert "2" in out
    assert "1" in out

def test_e2e_string_concat():
    if not GCC_AVAILABLE:
        print("  (ignoré : GCC non disponible)")
        return
    src = ('fun main()\n'
           '    first = "Air"\n'
           '    last  = "Lang"\n'
           '    print(first + last)\n'
           'end\nmain()')
    out, code = compile_and_run(src)
    assert "AirLang" in out

def test_e2e_blueprint_basic():
    if not GCC_AVAILABLE:
        print("  (ignoré : GCC non disponible)")
        return
    src = ('blueprint Greeter\n'
           '    name: String\n'
           '    fun hello()\n'
           '        print("Salut " + name)\n'
           '    end\n'
           'end\n'
           'fun main()\n'
           '    g = Greeter.new(name: "Monde")\n'
           '    g.hello()\n'
           'end\nmain()')
    out, code = compile_and_run(src)
    assert "Salut Monde" in out

def test_e2e_return_value():
    if not GCC_AVAILABLE:
        print("  (ignoré : GCC non disponible)")
        return
    src = ('fun add(a: Int, b: Int) -> Int\n'
           '    return a + b\n'
           'end\n'
           'fun main()\n'
           '    result = add(20, 22)\n'
           '    print(result)\n'
           'end\nmain()')
    out, code = compile_and_run(src)
    assert "42" in out


# ── Runner ────────────────────────────────────────────────────────────────────

def run_all_tests():
    tests = [
        (name, fn) for name, fn in globals().items()
        if name.startswith("test_") and callable(fn)
    ]
    passed = 0
    failed = 0
    errors = []
    skipped = 0

    print(f"\n── Tests Codegen AirLang ({len(tests)} tests) ──────────────────")
    if not GCC_AVAILABLE:
        print("  ⚠  GCC non disponible — les tests end-to-end seront ignorés")

    for name, fn in tests:
        try:
            fn()
            print(f"  ✓  {name}")
            passed += 1
        except Exception as e:
            msg = str(e)
            if "ignoré" in msg or "GCC non disponible" in msg:
                print(f"  ~  {name}  (ignoré)")
                skipped += 1
            else:
                print(f"  ✘  {name}")
                errors.append((name, traceback.format_exc()))
                failed += 1

    total_run = passed + failed
    print(f"\n── Résultat : {passed}/{total_run} réussis"
          + (f", {skipped} ignorés" if skipped else "")
          + " ──────────────────")

    if errors:
        print("\nDétail des échecs :")
        for name, tb in errors:
            print(f"\n  [{name}]")
            for line in tb.strip().splitlines()[-5:]:
                print(f"    {line}")
    else:
        print("  Tous les tests actifs ont réussi ✓")

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
