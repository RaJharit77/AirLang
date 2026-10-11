"""Tests de bout en bout : un programme .air est compilé, exécuté, et sa sortie vérifiée."""

import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from compiler import driver

ROOT = os.path.join(os.path.dirname(__file__), "..")
PROGRAMS = os.path.join(os.path.dirname(__file__), "programs")

pytestmark = pytest.mark.skipif(driver.find_c_compiler() is None, reason="aucun compilateur C")


def run_file(path: str):
    with open(path, encoding="utf-8") as f:
        src = f.read()
    c = driver.compile_to_c(src, path)
    with tempfile.TemporaryDirectory() as tmp:
        exe = os.path.join(tmp, "prog")
        driver.build_binary(c, exe)
        r = subprocess.run([exe], capture_output=True, text=True, timeout=10)
    return r.stdout, r.stderr, r.returncode


def test_features_program_matches_expected_output():
    out, _, code = run_file(os.path.join(PROGRAMS, "features.air"))
    with open(os.path.join(PROGRAMS, "features.expected"), encoding="utf-8") as f:
        assert out == f.read()
    assert code == 0


def test_hello_example():
    out, _, code = run_file(os.path.join(ROOT, "examples", "hello.air"))
    assert code == 0
    assert out.splitlines()[0] == "Bonjour, Monde !"
    assert out.splitlines()[-1] == "Itération 4"


def test_division_by_zero_is_a_clean_runtime_error():
    out, err, code = run_file(os.path.join(PROGRAMS, "div_zero.air"))
    assert out == "avant\n"
    assert "division par zéro" in err
    assert code == 1


def test_generated_c_compiles_without_warnings_in_strict_mode():
    cc = driver.find_c_compiler()
    with open(os.path.join(PROGRAMS, "features.air"), encoding="utf-8") as f:
        c = driver.compile_to_c(f.read(), "features.air")
    with tempfile.TemporaryDirectory() as tmp:
        cfile = os.path.join(tmp, "p.c")
        with open(cfile, "w", encoding="utf-8") as f:
            f.write(c)
        r = subprocess.run([cc, "-std=gnu11", "-Wall", "-Wextra", "-Wno-unused-parameter",
                            "-Wno-unused-function", "-Wno-unused-variable", "-Werror", "-fsyntax-only",
                            f"-I{driver.RUNTIME_DIR}", cfile], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
