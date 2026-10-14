"""Tests du formateur Rust (`air fmt`) : il ne doit JAMAIS changer les tokens d'un programme,
et formater deux fois doit donner le même résultat. Ignorés si le binaire n'est pas compilé
(`cd tools/air && cargo build --release`)."""

import glob
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from compiler.lexer import Lexer, TokenType

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
AIR = next((p for p in (os.path.join(ROOT, "tools", "air", "target", "release", "air"),
                        os.path.join(ROOT, "tools", "air", "target", "debug", "air"))
            if os.path.exists(p)), None)

pytestmark = pytest.mark.skipif(AIR is None, reason="binaire `air` non compilé (cargo build --release)")

FILES = sorted(glob.glob(os.path.join(ROOT, "examples", "*.air"))
               + glob.glob(os.path.join(ROOT, "stdlib", "*.air"))
               + glob.glob(os.path.join(ROOT, "tests", "programs", "*.air")))


def logical_tokens(src: str):
    """Tokens + une seule coupure entre lignes logiques (les lignes vides ne comptent pas)."""
    out, prev_nl = [], False
    for t in Lexer(src, "x").tokenize():
        if t.type == TokenType.NEWLINE:
            if not prev_nl:
                out.append(("NL",))
            prev_nl = True
        elif t.type != TokenType.EOF:
            out.append((t.type, t.value, repr(getattr(t, "parts", None))))
            prev_nl = False
    while out and out[0] == ("NL",):
        out.pop(0)
    while out and out[-1] == ("NL",):
        out.pop()
    return out


def fmt(path: str) -> str:
    r = subprocess.run([AIR, "fmt", "--stdout", path], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout


@pytest.mark.parametrize("path", FILES, ids=[os.path.relpath(f, ROOT) for f in FILES])
def test_formatting_preserves_tokens_and_is_idempotent(path, tmp_path):
    with open(path, encoding="utf-8") as f:
        src = f.read()
    once = fmt(path)
    assert logical_tokens(src) == logical_tokens(once)
    p2 = tmp_path / "again.air"
    p2.write_text(once, encoding="utf-8")
    assert fmt(str(p2)) == once


def test_check_mode_reports_unformatted_files(tmp_path):
    bad = tmp_path / "bad.air"
    bad.write_text("fun f()\nreturn 1\nend\n", encoding="utf-8")
    r = subprocess.run([AIR, "fmt", "--check", str(bad)], capture_output=True, text=True)
    assert r.returncode == 1 and "à reformater" in r.stdout
    assert bad.read_text(encoding="utf-8") == "fun f()\nreturn 1\nend\n"   # --check ne modifie rien
    subprocess.run([AIR, "fmt", str(bad)], check=True, capture_output=True)
    r = subprocess.run([AIR, "fmt", "--check", str(bad)], capture_output=True, text=True)
    assert r.returncode == 0


def test_unterminated_string_leaves_file_untouched(tmp_path):
    f = tmp_path / "x.air"
    f.write_text('x = "abc\n', encoding="utf-8")
    r = subprocess.run([AIR, "fmt", str(f)], capture_output=True, text=True)
    assert r.returncode == 2 and "chaîne non fermée" in r.stderr
    assert f.read_text(encoding="utf-8") == 'x = "abc\n'


def test_air_cli_delegates_to_the_compiler():
    r = subprocess.run([AIR, "run", os.path.join(ROOT, "examples", "hello.air")],
                       capture_output=True, text=True, env={**os.environ, "AIR_HOME": ROOT})
    assert r.returncode == 0 and r.stdout.splitlines()[0] == "Bonjour, Monde !"
