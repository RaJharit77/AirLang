"""`air test` : exécute les fonctions `test_*` d'un fichier (ou de tous les fichiers de test d'un dossier).

Principe : on ajoute à la fin du source un petit programme AirLang qui appelle chaque `test_*`
dans un `try/catch`, affiche le résultat, puis quitte avec le code 1 s'il y a des échecs.
Les numéros de ligne du fichier ne changent pas (l'ajout est en fin de fichier).
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from typing import List, Tuple

from . import driver
from .ast_nodes import ExportDecl, FunDecl
from .errors import AirError


def find_test_files(path: str) -> List[str]:
    if os.path.isfile(path):
        return [path]
    found: List[str] = []
    for root, dirs, files in os.walk(path):
        dirs[:] = sorted(d for d in dirs if not d.startswith((".", "_")) and d != "build")
        for name in sorted(files):
            if name.endswith(".air") and (name.startswith("test_") or name.endswith("_test.air")):
                found.append(os.path.join(root, name))
    return found


def test_functions(program) -> List[FunDecl]:
    funs = []
    for st in program.statements:
        d = st.declaration if isinstance(st, ExportDecl) else st
        if isinstance(d, FunDecl) and d.name.startswith("test_"):
            funs.append(d)
    return funs


def runner_source(names: List[str]) -> str:
    out = ["", "fun air_run_all_tests()", "    passed = 0", "    failed = 0"]
    for n in names:
        out += ["    try",
                f"        {n}()",
                "        passed += 1",
                f'        print("  ✔ {n}")',
                "    catch e",
                "        failed += 1",
                f'        print("  ✘ {n} : {{e.message}}")',
                "    end"]
    out += ['    print("{passed} réussi(s), {failed} échoué(s)")',
            "    if failed > 0",
            "        exit(1)",
            "    end",
            "end",
            "air_run_all_tests()", ""]
    return "\n".join(out)


def run_file(path: str) -> Tuple[int, int, str]:
    """Retourne (code, nombre_de_tests, sortie). code 0 = tout passe, 1 = échecs, 2 = erreur de compilation."""
    with open(path, encoding="utf-8") as f:
        source = f.read()
    program = driver.check(source, path)           # lève CompileErrors si le fichier est invalide
    funs = test_functions(program)
    for fn in funs:
        if fn.params:
            raise AirError(f"le test `{fn.name}` ne doit pas avoir de paramètres", fn.line, fn.column,
                           filename=path, source=source, hint="un test s'écrit `fun test_nom()`")
    if not funs:
        return 0, 0, "  (aucune fonction test_* dans ce fichier)\n"
    if not source.endswith("\n"):
        source += "\n"
    c_code = driver.compile_to_c(source + runner_source([f.name for f in funs]), path)
    with tempfile.TemporaryDirectory() as tmp:
        exe = os.path.join(tmp, "tests")
        driver.build_binary(c_code, exe)
        r = subprocess.run([exe], capture_output=True, text=True, timeout=120)
    return (0 if r.returncode == 0 else 1), len(funs), r.stdout + r.stderr
