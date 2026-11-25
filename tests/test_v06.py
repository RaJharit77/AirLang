"""Tests v0.6 : assert / assert_eq / exit, `air test`, blueprints et traits dans les modules."""

import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from compiler import driver
from compiler.driver import CompileErrors

pytestmark = pytest.mark.skipif(driver.find_c_compiler() is None, reason="aucun compilateur C")

ROOT = os.path.join(os.path.dirname(__file__), "..")


def run_src(src: str, filename: str = "t.air"):
    c = driver.compile_to_c(src, filename)
    with tempfile.TemporaryDirectory() as tmp:
        exe = os.path.join(tmp, "prog")
        driver.build_binary(c, exe)
        r = subprocess.run([exe], capture_output=True, text=True, timeout=10)
    return r.stdout, r.stderr, r.returncode


def prog(body: str, top: str = "") -> str:
    return top + "\nfun main()\n" + "".join("    " + l + "\n" for l in body.strip().splitlines()) + "end\nmain()\n"


def cli(*args, cwd=ROOT):
    return subprocess.run([sys.executable, "-m", "compiler", *args], capture_output=True, text=True,
                          cwd=cwd, timeout=120)


# ── assert / assert_eq / exit ────────────────────────────────────────────────

def test_assert_passes_and_fails_catchably():
    o, e, code = run_src(prog('''assert(1 + 1 == 2)
assert_eq("a" + "b", "ab")
try
    assert(1 > 2, "faux")
catch err
    print(err.message)
end
try
    assert_eq(1 + 1, 3)
catch err
    print(err.message)
end'''))
    assert code == 0, e
    assert o.splitlines() == ["faux (ligne 6)", "assert_eq : le premier vaut 2, le second vaut 3 (ligne 11)"]


def test_assert_uncaught_exits_with_error():
    o, e, code = run_src(prog('assert(false, "boum")'))
    assert code == 1 and "boum" in e


def test_exit_code_and_flush():
    o, e, code = run_src(prog('print("avant")\nexit(3)\nprint("jamais")'))
    assert code == 3 and o.strip() == "avant"


def test_assert_type_errors():
    with pytest.raises(CompileErrors) as ei:
        driver.compile_to_c(prog('assert(1)'), "t.air")
    assert "Bool" in str(ei.value.errors[0])
    with pytest.raises(CompileErrors) as ei:
        driver.compile_to_c(prog('assert_eq([1], [1])'), "t.air")
    assert "assert_eq" in str(ei.value.errors[0])


def test_exit_counts_as_leaving_function():
    src = '''fun f(x: Int) -> Int
    if x > 0
        return x
    end
    exit(2)
end
print(f(5))
'''
    o, e, code = run_src(src)
    assert code == 0 and o.strip() == "5"


# ── air test ─────────────────────────────────────────────────────────────────

def _write(tmp, name, text):
    path = os.path.join(tmp, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def test_air_test_all_pass():
    r = cli("test", "examples/tests")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "✔ test_addition" in r.stdout and "tout passe" in r.stdout


def test_air_test_reports_failures_and_exit_code():
    with tempfile.TemporaryDirectory() as tmp:
        p = _write(tmp, "test_x.air", "fun test_ok()\n    assert(true)\nend\n"
                                      "fun test_ko()\n    assert_eq(2 * 2, 5)\nend\n")
        r = cli("test", p)
    assert r.returncode == 1
    assert "✔ test_ok" in r.stdout and "✘ test_ko" in r.stdout and "1 réussi(s), 1 échoué(s)" in r.stdout


def test_air_test_directory_discovery_and_no_tests():
    with tempfile.TemporaryDirectory() as tmp:
        _write(tmp, "util.air", "fun x() -> Int\n    return 1\nend\n")
        r = cli("test", tmp)
        assert r.returncode == 2 and "aucun fichier de test" in r.stderr
        _write(tmp, "a_test.air", "fun test_a()\n    assert(true)\nend\n")
        r = cli("test", tmp)
        assert r.returncode == 0 and "✔ test_a" in r.stdout


def test_air_test_rejects_test_with_params_and_compile_errors():
    with tempfile.TemporaryDirectory() as tmp:
        p = _write(tmp, "test_p.air", "fun test_p(x: Int)\n    assert(true)\nend\n")
        r = cli("test", p)
        assert r.returncode == 1 and "ne doit pas avoir de paramètres" in r.stderr
        p = _write(tmp, "test_e.air", "fun test_e()\n    assert(1)\nend\n")
        r = cli("test", p)
        assert r.returncode == 1 and "Bool" in r.stderr


def test_function_ending_with_fail_needs_no_return():
    src = '''fun pick(x: Int) -> Int
    if x > 0
        return x
    end
    fail("négatif")
end
try
    print(pick(1))
    print(pick(-1))
catch e
    print(e.message)
end
'''
    o, e, code = run_src(src)
    assert code == 0 and o.split("\n")[:2] == ["1", "négatif"]


# ── Blueprints et traits dans les modules ────────────────────────────────────

SHAPES = '''const UNIT = 2
export trait Named
    fun label() -> String
end
export blueprint Shape implements Named
    name: String = "forme"
    fun label() -> String
        return name
    end
    fun area() -> Float
        return 0.0
    end
end
export blueprint Square extends Shape
    side: Float = 1.0
    fun area() -> Float
        return side * side * scale()
    end
end
fun scale() -> Float
    return 1.0
end
export fun unit_square() -> Square
    return Square.new(name: "carré", side: 1.0)
end
export fun total(shapes: List[Shape]) -> Float
    t = 0.0
    for s in shapes
        t += s.area()
    end
    return t
end
'''


def project(files):
    tmp = tempfile.mkdtemp()
    for name, text in files.items():
        with open(os.path.join(tmp, name), "w", encoding="utf-8") as f:
            f.write(text)
    return os.path.join(tmp, "main.air")


def run_project(files):
    main = project(files)
    with open(main, encoding="utf-8") as f:
        return run_src(f.read(), main)


def error_of(files):
    main = project(files)
    with open(main, encoding="utf-8") as f:
        src = f.read()
    with pytest.raises(CompileErrors) as ei:
        driver.compile_to_c(src, main)
    return "\n".join(str(e) for e in ei.value.errors)


def test_module_blueprints_inheritance_across_files():
    o, e, code = run_project({"shapes.air": SHAPES, "main.air": '''import "./shapes"
blueprint Circle extends shapes.Shape
    r: Float = 1.0
    fun area() -> Float
        return 3.0 * r * r
    end
end
fun describe(s: shapes.Shape) -> String
    return "<{s.label()}>"
end
sq = shapes.Square.new(name: "mon carré", side: 3.0)
c = Circle.new(name: "rond", r: 2.0)
u: shapes.Square = shapes.unit_square()
print(sq.area(), c.area(), u.area(), describe(sq), describe(c))
print(shapes.total([sq, c, u]))
'''})
    assert code == 0, e
    assert o.splitlines() == ["9.0 12.0 1.0 <mon carré> <rond>", "22.0"]


def test_module_type_errors_are_demangled_and_visibility_enforced():
    e = error_of({"shapes.air": SHAPES, "main.air": 'import "./shapes"\nx: Int = shapes.unit_square()\n'})
    assert "__" not in e.split("-->")[0] and "Square" in e
    e = error_of({"shapes.air": SHAPES.replace("export blueprint Square", "blueprint Square"),
                  "main.air": 'import "./shapes"\ns = shapes.Square.new()\n'})
    assert "n'est pas exporté" in e
    e = error_of({"shapes.air": SHAPES, "main.air": 'import "./shapes"\ns = shapes.Nope.new()\n'})
    assert "n'a pas de type `Nope`" in e and "Square" in e


def test_mixed_list_literals_use_expected_type_and_common_ancestor():
    top = '''blueprint A
    fun n() -> Int
        return 1
    end
end
blueprint B extends A
    fun n() -> Int
        return 2
    end
end
blueprint C extends A
    fun n() -> Int
        return 3
    end
end'''
    body = '''xs: List[A] = [B.new(), C.new(), A.new()]
ys = [B.new(), C.new()]
t = 0
for x in xs
    t += x.n()
end
for y in ys
    t += y.n()
end
print(t)'''
    o, e, code = run_src(top + "\nfun main()\n" + "".join("    " + l + "\n" for l in body.splitlines()) + "end\nmain()\n")
    assert code == 0, e
    assert o.strip() == "11"
    with pytest.raises(CompileErrors):
        driver.compile_to_c(top + "\nxs: List[B] = [B.new(), C.new()]\n", "t.air")
