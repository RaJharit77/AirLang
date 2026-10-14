"""
AirLang — driver.py
Enchaîne les étapes : source → lexer → parser → type checker → codegen C → gcc.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from typing import List, Optional

from .ast_nodes import Program
from .codegen_c import CCodegen
from .errors import AirError, CodegenError
from .lexer import Lexer
from .parser import Parser
from .type_checker import TypeChecker

__version__ = "0.3.0"

RUNTIME_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "runtime"))


class CompileErrors(Exception):
    """Une ou plusieurs erreurs AirLang empêchent la compilation."""

    def __init__(self, errors: List[AirError]):
        super().__init__(f"{len(errors)} erreur(s)")
        self.errors = errors


def parse(source: str, filename: str = "<source>") -> Program:
    tokens = Lexer(source, filename).tokenize()
    return Parser(tokens, source=source, filename=filename).parse()


def check(source: str, filename: str = "<source>") -> Program:
    """Lexe, parse et vérifie. Lève CompileErrors s'il y a des erreurs."""
    try:
        program = parse(source, filename)
    except AirError as e:
        raise CompileErrors([e])
    checker = TypeChecker(source, filename)
    errors = checker.check(program)
    if errors:
        raise CompileErrors(list(errors))
    return program


def compile_to_c(source: str, filename: str = "<source>") -> str:
    program = check(source, filename)
    try:
        return CCodegen(source, filename).generate(program)
    except CodegenError as e:
        raise CompileErrors([e])


def find_c_compiler() -> Optional[str]:
    for cand in (os.environ.get("CC"), "gcc", "cc", "clang"):
        if cand and shutil.which(cand):
            return cand
    return None


def build_binary(c_code: str, output: str, optimize: bool = True) -> None:
    """Compile le C généré avec le runtime. Lève RuntimeError en cas d'échec."""
    cc = find_c_compiler()
    if cc is None:
        raise RuntimeError("aucun compilateur C trouvé (installez gcc ou clang)")
    with tempfile.TemporaryDirectory() as tmp:
        c_file = os.path.join(tmp, "prog.c")
        with open(c_file, "w", encoding="utf-8") as f:
            f.write(c_code)
        sources = [c_file] + [os.path.join(RUNTIME_DIR, n)
                              for n in ("air_runtime.c", "air_stdlib.c")
                              if os.path.exists(os.path.join(RUNTIME_DIR, n))]
        cmd = [cc, "-std=gnu11", "-O1" if optimize else "-O0", "-w", "-o", output,
               f"-I{RUNTIME_DIR}"] + sources + ["-lm"]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            raise RuntimeError("le C généré n'a pas compilé (bug du compilateur AirLang) :\n"
                               + res.stderr)
