"""Tests v0.5 : imports de fichiers, export, cycles, modules standard string et list."""

import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from compiler import driver
from compiler.driver import CompileErrors

pytestmark = pytest.mark.skipif(driver.find_c_compiler() is None, reason="aucun compilateur C")


def project(files: dict, main: str = "main.air"):
    """Écrit les fichiers dans un dossier temporaire ; retourne (dossier, chemin du principal)."""
    tmp = tempfile.mkdtemp()
    for name, text in files.items():
        path = os.path.join(tmp, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    return tmp, os.path.join(tmp, main)


def run_project(files: dict) -> str:
    _, main = project(files)
    with open(main, encoding="utf-8") as f:
        c = driver.compile_to_c(f.read(), main)
    with tempfile.TemporaryDirectory() as tmp:
        exe = os.path.join(tmp, "prog")
        driver.build_binary(c, exe)
        r = subprocess.run([exe], capture_output=True, text=True, timeout=10)
    assert r.returncode == 0, r.stderr
    return r.stdout


def error_of(files: dict) -> str:
    _, main = project(files)
    with open(main, encoding="utf-8") as f:
        src = f.read()
    with pytest.raises(CompileErrors) as ei:
        driver.compile_to_c(src, main)
    return "\n".join(str(e) for e in ei.value.errors)


GEO = '''import math
const SCALE = 2
export fun area(r: Float) -> Float
    return math.PI * r * r * helper()
end
fun helper() -> Float
    return 1.0
end
export fun scaled(n: Int) -> Int
    return n * SCALE
end
'''


def test_file_import_alias_and_private_names():
    o = run_project({
        "lib/geo.air": GEO,
        "main.air": '''import "./lib/geo"
import "./lib/geo" as g
fun helper() -> String
    return "mien"
end
print(geo.area(1.0) > 3.14, g.scaled(21), helper())
''',
    })
    assert o.strip() == "true 42 mien"


def test_nested_and_shared_imports_load_once():
    o = run_project({
        "a.air": 'import "./c"\nexport fun fa() -> Int\n    return c.fc() + 1\nend\n',
        "b.air": 'import "./c"\nexport fun fb() -> Int\n    return c.fc() + 2\nend\n',
        "c.air": 'const BASE = 10\nexport fun fc() -> Int\n    return BASE\nend\n',
        "main.air": 'import "./a"\nimport "./b"\nprint(a.fa(), b.fb())\n',
    })
    assert o.strip() == "11 12"


def test_not_exported_is_error():
    e = error_of({"lib/geo.air": GEO, "main.air": 'import "./lib/geo"\nprint(geo.helper())\n'})
    assert "n'est pas exporté" in e and "main.air:2" in e


def test_unknown_member_lists_available():
    e = error_of({"lib/geo.air": GEO, "main.air": 'import "./lib/geo"\nprint(geo.zzz())\n'})
    assert "n'a pas de `zzz`" in e and "area" in e


def test_missing_file_error():
    e = error_of({"main.air": 'import "./nope"\n'})
    assert "fichier introuvable" in e


def test_cycle_detected():
    e = error_of({
        "a.air": 'import "./b"\nexport fun fa() -> Int\n    return b.fb()\nend\n',
        "b.air": 'import "./a"\nexport fun fb() -> Int\n    return a.fa()\nend\n',
        "main.air": 'import "./a"\nprint(a.fa())\n',
    })
    assert "import circulaire" in e and "a.air -> b.air -> a.air" in e


def test_type_error_in_module_points_to_module_file():
    e = error_of({"bad.air": 'export fun f() -> Int\n    return "x"\nend\n',
                  "main.air": 'import "./bad"\nprint(bad.f())\n'})
    assert "bad.air:2" in e


def test_module_rejects_statements_and_blueprints():
    e = error_of({"m.air": 'print("hi")\n', "main.air": 'import "./m"\n'})
    assert "non supportée dans un module" in e
    e = error_of({"m.air": 'export blueprint P\n    x: Int = 1\nend\n', "main.air": 'import "./m"\n'})
    assert "v0.6" in e


def test_local_names_shadow_module_names():
    # `min` est à la fois une fonction du module et un paramètre/variable locale
    o = run_project({
        "m.air": '''export fun min(a: Int, b: Int) -> Int
    if a < b
        return a
    end
    return b
end
export fun clamp(min: Int, max: Int, x: Int) -> Int
    f = fun(max: Int) => max + 0
    for min2 in [1]
        x = x + min2 - 1
    end
    if x < min
        return min
    end
    return f(max)
end
''',
        "main.air": 'import "./m"\nprint(m.min(3, 2), m.clamp(0, 10, 5))\n',
    })
    assert o.strip() == "2 10"


def test_stdlib_string_and_list():
    o = run_project({"main.air": '''import string
import list
print(string.repeat("ab", 3), string.pad_left("7", 3, "0"), string.reverse("héllo"), string.count("a,b,c", ","))
print(list.range(1, 5), list.sum([1, 2, 3]), list.max_int([3, 9, 2]), list.max_int(list.range(0, 0)), list.average([1.0, 2.0, 6.0]))
'''})
    assert o.splitlines() == ["ababab 007 olléh 2", "[1, 2, 3, 4] 6 9 null 3.0"]


def test_example_modules_runs():
    root = os.path.join(os.path.dirname(__file__), "..", "examples", "modules", "main.air")
    with open(root, encoding="utf-8") as f:
        c = driver.compile_to_c(f.read(), root)
    with tempfile.TemporaryDirectory() as tmp:
        exe = os.path.join(tmp, "prog")
        driver.build_binary(c, exe)
        r = subprocess.run([exe], capture_output=True, text=True, timeout=10)
    assert r.returncode == 0 and "Somme de [1, 2, 3, 4, 5] : 15" in r.stdout
