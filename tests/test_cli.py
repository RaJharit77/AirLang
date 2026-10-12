"""Tests de la CLI `airc` / `air`."""

import os
import subprocess
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..")
AIRC = [sys.executable, os.path.join(ROOT, "airc.py")]
HELLO = os.path.join(ROOT, "examples", "hello.air")


def air(*args):
    return subprocess.run(AIRC + list(args), capture_output=True, text=True, timeout=30)


def test_version_and_help():
    assert "AirLang 0." in air("version").stdout
    assert "air run" in air("help").stdout

def test_run():
    r = air("run", HELLO)
    assert r.returncode == 0 and r.stdout.startswith("Bonjour, Monde !")

def test_legacy_invocation_still_works():
    assert air(HELLO).stdout.startswith("Bonjour, Monde !")

def test_check_ok_and_failure(tmp_path):
    assert air("check", HELLO).returncode == 0
    bad = tmp_path / "bad.air"
    bad.write_text("print(inconnu)\n", encoding="utf-8")
    r = air("check", str(bad))
    assert r.returncode == 1
    assert "variable inconnue `inconnu`" in r.stderr and "1 erreur" in r.stderr

def test_emit_c_and_ast_and_tokens():
    assert "int main(void)" in air("emit-c", HELLO).stdout
    assert "Program" in air("ast", HELLO).stdout
    assert "IDENTIFIER" in air("tokens", HELLO).stdout.upper() or "IDENT" in air("tokens", HELLO).stdout.upper()

def test_build_produces_executable(tmp_path):
    out = tmp_path / "hello"
    assert air("build", HELLO, "-o", str(out)).returncode == 0
    r = subprocess.run([str(out)], capture_output=True, text=True)
    assert r.stdout.startswith("Bonjour, Monde !")

def test_missing_file():
    r = air("run", "nope.air")
    assert r.returncode == 1 and "introuvable" in r.stderr
