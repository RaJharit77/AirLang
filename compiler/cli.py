"""
AirLang — cli.py
Interface en ligne de commande : air run | build | check | emit-c | tokens | ast | version | help
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from typing import List, Optional

from . import driver
from .ast_nodes import pretty
from .driver import CompileErrors, __version__
from .errors import AirError, AirIOError
from .lexer import Lexer, TokenType

HELP = f"""\
AirLang {__version__} — Simple comme respirer. Léger comme l'air.

Usage :
    air run   <fichier.air>            Compile et exécute
    air build <fichier.air> [-o sortie]  Compile vers un exécutable
    air check <fichier.air>            Vérifie sans compiler
    air emit-c <fichier.air>           Affiche le C généré
    air tokens <fichier.air>           Affiche les tokens
    air ast   <fichier.air>            Affiche l'AST
    air version | help

(`airc fichier.air [--ast|--tokens|--check]` reste accepté.)
"""

COMMANDS = {"run", "build", "check", "emit-c", "tokens", "ast", "version", "help"}


def _color() -> bool:
    return sys.stderr.isatty() and not os.environ.get("NO_COLOR")


def _report(errors: List[AirError]) -> None:
    color = _color()
    for e in errors:
        print(e.format(color=color), file=sys.stderr)
        print(file=sys.stderr)
    n = len(errors)
    print(f"{n} erreur{'s' if n > 1 else ''} — compilation interrompue.", file=sys.stderr)


def _read(path: str) -> str:
    if not os.path.isfile(path):
        raise CompileErrors([AirIOError(f"fichier introuvable : `{path}`",
                                        hint="vérifiez le chemin du fichier .air")])
    if not path.endswith(".air"):
        print(f"avertissement : `{path}` n'a pas l'extension .air", file=sys.stderr)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def main(argv: Optional[List[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help", "help"):
        print(HELP)
        return 0
    if args[0] in ("-V", "--version", "version"):
        print(f"AirLang {__version__}")
        return 0

    # Compatibilité : `airc fichier.air [--ast|--tokens|--check]`
    if args[0] not in COMMANDS:
        legacy = {"--ast": "ast", "--tokens": "tokens", "--check": "check", "--emit-c": "emit-c"}
        cmd = next((legacy[a] for a in args[1:] if a in legacy), "run")
        args = [cmd, args[0]] + [a for a in args[1:] if a not in legacy]

    cmd, rest = args[0], args[1:]
    out_path = None
    if "-o" in rest:
        i = rest.index("-o")
        if i + 1 >= len(rest):
            print("erreur : `-o` attend un nom de fichier", file=sys.stderr)
            return 2
        out_path = rest[i + 1]
        del rest[i:i + 2]
    if not rest:
        print(f"erreur : `air {cmd}` attend un fichier .air\n", file=sys.stderr)
        print(HELP, file=sys.stderr)
        return 2
    path, prog_args = rest[0], rest[1:]

    try:
        source = _read(path)

        if cmd == "tokens":
            for t in Lexer(source, path).tokenize():
                if t.type not in (TokenType.NEWLINE, TokenType.EOF):
                    print(t)
            return 0
        if cmd == "ast":
            print(pretty(driver.check(source, path)))
            return 0
        if cmd == "check":
            driver.check(source, path)
            print(f"✓ {path} : aucune erreur")
            return 0

        c_code = driver.compile_to_c(source, path)
        if cmd == "emit-c":
            sys.stdout.write(c_code)
            return 0

        if cmd == "build":
            out = out_path or os.path.splitext(os.path.basename(path))[0]
            driver.build_binary(c_code, out)
            print(f"✓ {path} → {out}")
            return 0

        # run
        with tempfile.TemporaryDirectory() as tmp:
            exe = os.path.join(tmp, "prog")
            driver.build_binary(c_code, exe)
            return subprocess.run([exe] + prog_args).returncode

    except CompileErrors as ce:
        _report(ce.errors)
        return 1
    except AirError as e:
        _report([e])
        return 1
    except RuntimeError as e:
        print(f"erreur interne : {e}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
