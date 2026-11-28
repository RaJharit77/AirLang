"""Tests v0.7 : ramasse-miettes conservatif (mémoire libérée, résultats inchangés, cycles, try/catch)."""

import glob
import os
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from compiler import driver

pytestmark = pytest.mark.skipif(driver.find_c_compiler() is None or sys.platform != "linux",
                                reason="le GC n'est actif que sous Linux avec gcc/clang")

ROOT = os.path.join(os.path.dirname(__file__), "..")


def build(src: str, filename: str = "t.air") -> str:
    c = driver.compile_to_c(src, filename)
    tmp = tempfile.mkdtemp()
    exe = os.path.join(tmp, "prog")
    driver.build_binary(c, exe)
    return exe


def run(exe: str, **env):
    e = dict(os.environ)
    e.pop("AIR_GC_STRESS", None)
    e.update({k: str(v) for k, v in env.items()})
    r = subprocess.run([exe], capture_output=True, text=True, timeout=120, env=e)
    return r.stdout, r.stderr, r.returncode


def stats(stderr: str) -> dict:
    m = re.search(r"\[air-gc\] collectes=(\d+) allocations=(\d+) octets_alloués=(\d+) octets_libérés=(\d+) "
                  r"pic_vivant=(\d+) vivant_final=(\d+)", stderr)
    assert m, stderr
    keys = ("collections", "allocs", "alloc_bytes", "freed_bytes", "peak", "live")
    return dict(zip(keys, map(int, m.groups())))


CHURN = '''blueprint Node
    value: Int = 0
    next: Node? = null
end

fun build(n: Int) -> String
    s = ""
    i = 0
    while i < n
        s = s + "x"
        i += 1
    end
    return s
end

fun main()
    keep = [1, 2, 3]
    names = {"a": "alpha"}
    total = 0
    i = 0
    while i < 20000
        total += build(50).length()
        total += "a,b,c,{i}".split(",").length()
        n = Node.new(value: i)
        m = Node.new(value: i + 1)
        n.next = m
        total += m.value
        i += 1
    end
    print(total, keep, names["a"])
end
main()
'''


def test_memory_is_reclaimed_and_result_unchanged():
    exe = build(CHURN)
    o_gc, e_gc, c1 = run(exe, AIR_GC_STATS=1)
    o_off, _, c2 = run(exe, AIR_GC=0)
    assert c1 == 0 and c2 == 0 and o_gc == o_off == "201090000 [1, 2, 3] alpha\n"
    s = stats(e_gc)
    assert s["collections"] >= 1
    assert s["freed_bytes"] > s["alloc_bytes"] // 2          # l'essentiel est récupéré
    assert s["peak"] < 40 * 1024 * 1024                        # ~31 Mo alloués au total : le pic reste borné


def test_cycles_are_collected():
    src = '''blueprint Cell
    other: Cell? = null
    pad: List[Int] = [0, 0, 0, 0, 0, 0, 0, 0]
end
fun main()
    i = 0
    count = 0
    while i < 300000
        a = Cell.new()
        b = Cell.new()
        a.other = b
        b.other = a
        count += 1
        i += 1
    end
    print(count)
end
main()
'''
    o, e, code = run(build(src), AIR_GC_STATS=1)
    assert code == 0 and o.strip() == "300000"
    s = stats(e)
    assert s["collections"] >= 2 and s["freed_bytes"] > 0
    assert s["peak"] < 0.6 * s["alloc_bytes"]                  # sans GC, le pic vaudrait alloc_bytes


def test_gc_disabled_by_env():
    _, e, _ = run(build(CHURN), AIR_GC_STATS=1, AIR_GC=0)
    assert "[air-gc]" not in e


def test_stress_mode_keeps_try_catch_closures_maps_optionals_correct():
    src = '''fun make_counter(start: Int) -> Fun[Int, Int]
    label = "n{start}"
    return fun(x: Int) => x + label.length() + start
end

fun parse(s: String) -> Float?
    n = s.to_float()
    if n == null
        return null
    end
    return n * 2.0
end

fun risky(i: Int) -> Result[String]
    if i % 3 == 0
        return Err("trois {i}")
    end
    return Ok("ok{i}")
end

fun main()
    f = make_counter(10)
    m = {"k": "v"}
    xs: List[String] = []
    total = 0
    for i in 0..30
        xs.append("item{i}")
        total += f(i)
        try
            if i % 7 == 0
                fail("boum {i}")
            end
        catch e
            xs.append(e.message)
        end
        match risky(i)
            Ok(v) => xs.append(v)
            Err(msg) => xs.append(msg)
        end
        p = parse("{i}.5")
        if p != null
            total += 1
        end
    end
    print(total, xs.length(), xs[0], xs[xs.length() - 1], m["k"])
end
main()
'''
    exe = build(src)
    normal, _, c1 = run(exe)
    stress, e2, c2 = run(exe, AIR_GC_STRESS=1)
    assert c1 == 0 and c2 == 0, e2
    assert normal == stress and normal.startswith("")


PROGRAMS = [p for p in sorted(glob.glob(os.path.join(ROOT, "tests", "programs", "*.air")))
            if os.path.exists(p[:-4] + ".expected")]


@pytest.mark.parametrize("path", PROGRAMS)
def test_test_programs_identical_under_gc_stress(path):
    with open(path, encoding="utf-8") as f:
        src = f.read()
    expected = open(path[:-4] + ".expected", encoding="utf-8").read()
    exe = build(src, path)
    out, err, code = run(exe, AIR_GC_STRESS=1)
    assert code == 0, err
    assert out == expected


# ── Traits comme types de valeur ─────────────────────────────────────────────

from compiler.driver import CompileErrors

TRAIT_TOP = '''trait Named
    fun label() -> String
    fun scaled(k: Int) -> Int
end
blueprint Dog implements Named
    fun label() -> String
        return "Dog"
    end
    fun scaled(k: Int) -> Int
        return k * 2
    end
end
blueprint Puppy extends Dog
    fun label() -> String
        return "Puppy"
    end
end
blueprint Rock
    fun weight() -> Int
        return 9
    end
end
'''


def run_main(body: str, top: str = TRAIT_TOP):
    src = top + "\nfun main()\n" + "".join("    " + l + "\n" for l in body.strip().splitlines()) + "end\nmain()\n"
    exe = build(src)
    return run(exe), run(exe, AIR_GC_STRESS=1)


def test_trait_param_variable_list_and_dynamic_dispatch():
    (o, e, c), (o2, e2, c2) = run_main('''x: Named = Puppy.new()
items: List[Named] = [Dog.new(), Puppy.new()]
t = 0
for it in items
    print(it.label())
    t += it.scaled(21)
end
print(x.label(), t)''')
    assert c == 0 and o.splitlines() == ["Dog", "Puppy", "Puppy 84"], e
    assert (o2, c2) == (o, c)                      # identique avec une collecte à chaque allocation


def test_trait_function_arguments_and_returns():
    top = TRAIT_TOP + '''fun pick(flag: Bool) -> Named
    if flag
        return Dog.new()
    end
    return Puppy.new()
end
fun describe(n: Named) -> String
    return "<{n.label()}>"
end
'''
    (o, e, c), _ = run_main('print(describe(pick(true)), describe(pick(false)), describe(Dog.new()))', top)
    assert c == 0 and o.strip() == "<Dog> <Puppy> <Dog>", e


def test_trait_errors():
    with pytest.raises(CompileErrors):                           # Rock n'implémente pas Named
        driver.compile_to_c(TRAIT_TOP + "x: Named = Rock.new()\n", "t.air")
    with pytest.raises(CompileErrors) as ei:                    # méthode inconnue
        driver.compile_to_c(TRAIT_TOP + "x: Named = Dog.new()\nprint(x.nope())\n", "t.air")
    assert "n'a pas de méthode `nope`" in str(ei.value.errors[0])
    with pytest.raises(CompileErrors) as ei:                    # optionnel : pas encore
        driver.compile_to_c(TRAIT_TOP + "x: Named? = null\n", "t.air")
    assert "optionnel" in str(ei.value.errors[0])


def test_trait_exported_from_module():
    tmp = tempfile.mkdtemp()
    with open(os.path.join(tmp, "shapes.air"), "w", encoding="utf-8") as f:
        f.write('''export trait Named
    fun label() -> String
end
export blueprint Cat implements Named
    fun label() -> String
        return "Cat"
    end
end
export fun show(n: Named) -> String
    return "[{n.label()}]"
end
''')
    main = os.path.join(tmp, "main.air")
    src = 'import "./shapes"\nx: shapes.Named = shapes.Cat.new()\nprint(shapes.show(x), x.label())\n'
    exe = build(src, main)
    o, e, c = run(exe)
    assert c == 0 and o.strip() == "[Cat] Cat", e
