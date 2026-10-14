"""Tests v0.3 : listes, maps, boucles (break/continue), héritage, erreurs d'exécution."""

import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from compiler import driver
from compiler.driver import CompileErrors

ROOT = os.path.join(os.path.dirname(__file__), "..")
PROGRAMS = os.path.join(os.path.dirname(__file__), "programs")

pytestmark = pytest.mark.skipif(driver.find_c_compiler() is None, reason="aucun compilateur C")


def run_src(src: str, name: str = "t.air"):
    c = driver.compile_to_c(src, name)
    with tempfile.TemporaryDirectory() as tmp:
        exe = os.path.join(tmp, "prog")
        driver.build_binary(c, exe)
        r = subprocess.run([exe], capture_output=True, text=True, timeout=10)
    return r.stdout, r.stderr, r.returncode


def run_file(path: str):
    with open(path, encoding="utf-8") as f:
        return run_src(f.read(), path)


def prog(body: str) -> str:
    return "fun main()\n" + "".join("    " + l + "\n" for l in body.strip().splitlines()) + "end\nmain()\n"


@pytest.mark.parametrize("name", ["collections", "inheritance", "loops"])
def test_program_matches_expected_output(name):
    out, _, code = run_file(os.path.join(PROGRAMS, name + ".air"))
    with open(os.path.join(PROGRAMS, name + ".expected"), encoding="utf-8") as f:
        assert out == f.read()
    assert code == 0


@pytest.mark.parametrize("name,fragment", [
    ("index_oob", "hors limites"),
    ("missing_key", "introuvable"),
])
def test_runtime_errors_are_clean(name, fragment):
    out, err, code = run_file(os.path.join(PROGRAMS, name + ".air"))
    assert fragment in err
    assert "Erreur d'exécution" in err
    assert code == 1


def test_students_example_prints_float_averages():
    out, _, code = run_file(os.path.join(ROOT, "examples", "students.air"))
    assert code == 0
    assert "Ben : moyenne 9.5" in out
    assert "M. Dupont (professeur)" in out


# ── listes ────────────────────────────────────────────────────────────────────

def test_list_of_strings_and_floats_are_stored_by_value():
    out, _, _ = run_src(prog('xs = ["a", "b"]\nfs = [1.5, 2.5]\nprint(xs, fs)\nprint(xs[1] + fs[0])'
                             .replace("xs[1] + fs[0]", 'xs[1], fs[0]')))
    assert out == '["a", "b"] [1.5, 2.5]\nb 1.5\n'


def test_list_methods():
    out, _, _ = run_src(prog(
        'xs = [3, 1, 2]\nprint(xs.contains(2), xs.index_of(9), xs.first(), xs.last())\n'
        'print(xs.pop(), xs)\nprint(xs.remove_at(0), xs)\nxs.clear()\nprint(xs.length())\n'
        'print([1, 2, 3].reverse())'))
    assert out == "true -1 3 2\n2 [3, 1]\n3 [1]\n0\n[3, 2, 1]\n"


def test_sort_does_not_modify_original():
    out, _, _ = run_src(prog('xs = [3, 1, 2]\nys = xs.sort()\nprint(xs, ys)'))
    assert out == "[3, 1, 2] [1, 2, 3]\n"


def test_index_assignment_and_compound():
    out, _, _ = run_src(prog('xs = [1, 2]\nxs[0] = 10\nxs[1] *= 5\nprint(xs)'))
    assert out == "[10, 10]\n"


def test_split_and_join_roundtrip():
    out, _, _ = run_src(prog('parts = "a,b,c".split(",")\nprint(parts.length(), parts.join("+"))'))
    assert out == "3 a+b+c\n"


def test_list_of_blueprints_shares_references():
    src = ('blueprint P\n    n: Int\nend\n'
           + prog('p = P.new(n: 1)\nxs = [p]\nxs[0].n = 7\nprint(p.n)'))
    out, _, _ = run_src(src)
    assert out == "7\n"


# ── maps ──────────────────────────────────────────────────────────────────────

def test_map_methods_and_insertion_order():
    out, _, _ = run_src(prog(
        'm = {"b": 1, "a": 2}\nm["c"] = 3\nm.delete("b")\n'
        'print(m.keys(), m.values(), m.has("a"), m.has("b"), m.length())'))
    assert out == '["a", "c"] [2, 3] true false 2\n'


def test_map_get_or_default():
    out, _, _ = run_src(prog('m = {"a": 1}\nprint(m.get_or("a", 0), m.get_or("z", 42))'))
    assert out == "1 42\n"


def test_map_with_non_string_keys_is_a_clear_error():
    with pytest.raises(CompileErrors) as e:
        driver.compile_to_c(prog('m: Map[Int, Int] = {}\nprint(m.length())'), "t.air")
    assert "clés" in str(e.value.errors[0])


# ── boucles ───────────────────────────────────────────────────────────────────

def test_break_and_continue_in_for_and_while():
    out, _, _ = run_src(prog(
        'for i in 0..10\n    if i == 2 then continue end\n    if i == 5 then break end\n    print(i)\nend'))
    assert out == "0\n1\n3\n4\n"


def test_break_outside_loop_is_an_error():
    with pytest.raises(CompileErrors):
        driver.compile_to_c(prog("break"), "t.air")


def test_one_line_if_then_end_and_else_if_then():
    out, _, _ = run_src(prog(
        'x = 5\nif x > 3 then print("grand") end\n'
        'if x > 9 then print("énorme") else if x > 4 then print("moyen") else print("petit") end'))
    assert out == "grand\nmoyen\n"


# ── héritage ──────────────────────────────────────────────────────────────────

ANIMALS = '''blueprint Animal
    name: String
    fun sound() -> String
        return "..."
    end
    fun speak()
        print("{name} dit {sound()}")
    end
end
blueprint Dog extends Animal
    fun sound() -> String
        return "Wouf"
    end
end
blueprint Puppy extends Dog
    fun sound() -> String
        return "Wif"
    end
end
'''


def test_three_level_inheritance_dispatches_dynamically():
    out, _, _ = run_src(ANIMALS + prog(
        'zoo: List[Animal] = [Animal.new(name: "X"), Dog.new(name: "Rex"), Puppy.new(name: "Mini")]\n'
        'for a in zoo\n    a.speak()\nend'))
    assert out == "X dit ...\nRex dit Wouf\nMini dit Wif\n"


def test_inherited_method_not_overridden_is_found():
    out, _, _ = run_src(ANIMALS + prog('d = Dog.new(name: "Rex")\nd.speak()\nprint(d.name)'))
    assert out == "Rex dit Wouf\nRex\n"


def test_override_with_different_signature_is_rejected():
    src = ('blueprint A\n    fun f(x: Int) -> Int\n        return x\n    end\nend\n'
           'blueprint B extends A\n    fun f(x: String) -> Int\n        return 1\n    end\nend\n'
           + prog("print(1)"))
    with pytest.raises(CompileErrors) as e:
        driver.compile_to_c(src, "t.air")
    assert "même signature" in str(e.value.errors[0])


def test_generated_c_is_clean_in_strict_mode():
    cc = driver.find_c_compiler()
    for name in ("collections", "inheritance", "loops"):
        with open(os.path.join(PROGRAMS, name + ".air"), encoding="utf-8") as f:
            c = driver.compile_to_c(f.read(), name + ".air")
        with tempfile.TemporaryDirectory() as tmp:
            cfile = os.path.join(tmp, "p.c")
            with open(cfile, "w", encoding="utf-8") as f:
                f.write(c)
            r = subprocess.run([cc, "-std=gnu11", "-Wall", "-Wextra", "-Wno-unused-parameter",
                                "-Wno-unused-function", "-Wno-unused-variable", "-Werror",
                                "-fsyntax-only", f"-I{driver.RUNTIME_DIR}", cfile],
                               capture_output=True, text=True)
        assert r.returncode == 0, name + "\n" + r.stderr
