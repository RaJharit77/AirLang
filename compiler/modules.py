"""Résolution des modules de la bibliothèque standard (`import io`, `import math`).

v0.4 : seuls les modules du dossier `stdlib/` sont supportés. Le principe est volontairement
simple : le module est parsé, ses noms sont préfixés (`math.floor` -> `math__floor`), puis ses
déclarations sont ajoutées au programme et les accès `math.floor(...)` sont réécrits en appels
directs. Les imports de fichiers utilisateur (`import "./utils"`) viennent en v0.5.
"""

from __future__ import annotations

import dataclasses
import os
from typing import Dict, List, Optional, Set

from .ast_nodes import (Call, ExportDecl, FunDecl, Identifier, ImportDecl, MemberAccess,
                        MethodCall, Node, Program, VarDecl, Param)
from .errors import AirError, AirNameError
from .lexer import Lexer
from .parser import Parser

STDLIB_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "stdlib"))
SUPPORTED = ("io", "math")          # modules dont toutes les fonctions sont implémentées en v0.4


def _children(node: Node):
    for f in dataclasses.fields(node):
        if f.name == "ty":
            continue
        yield f.name, getattr(node, f.name)


def _walk_replace(value, fn):
    """Applique `fn` à chaque nœud (bas en haut) et remplace le résultat dans son parent."""
    if isinstance(value, Node):
        for name, child in _children(value):
            new = _walk_replace(child, fn)
            if new is not child:
                setattr(value, name, new)
        return fn(value)
    if isinstance(value, list):
        for i, item in enumerate(value):
            value[i] = _walk_replace(item, fn)
        return value
    if isinstance(value, tuple):
        items = tuple(_walk_replace(v, fn) for v in value)
        return items if any(a is not b for a, b in zip(items, value)) else value
    return value


def _local_names(fun: FunDecl) -> Set[str]:
    names = {p.name for p in fun.params}

    def collect(n):
        if isinstance(n, VarDecl):
            names.add(n.name)
        return n
    _walk_replace(fun.body, collect)
    return names


def _load(name: str) -> Program:
    path = os.path.join(STDLIB_DIR, name + ".air")
    with open(path, encoding="utf-8") as f:
        src = f.read()
    return Parser(Lexer(src, path).tokenize(), source=src, filename=path).parse()


def _mangle_module(prog: Program, mod: str) -> Dict[str, str]:
    """Préfixe les déclarations de premier niveau du module ; retourne {nom: nom_préfixé}."""
    table: Dict[str, str] = {}
    decls: List[Node] = []
    for st in prog.statements:
        d = st.declaration if isinstance(st, ExportDecl) else st
        if isinstance(d, (FunDecl, VarDecl)):
            table[d.name] = f"{mod}__{d.name}"
            decls.append(d)

    for d in decls:
        shadow = _local_names(d) if isinstance(d, FunDecl) else set()

        def ren(n, shadow=shadow):
            if isinstance(n, Identifier) and n.name in table and n.name not in shadow:
                n.name = table[n.name]
            return n
        if isinstance(d, FunDecl):
            _walk_replace(d.body, ren)
            for p in d.params:
                if p.default is not None:
                    p.default = _walk_replace(p.default, ren)
        elif d.value is not None:
            d.value = _walk_replace(d.value, ren)
    for d in decls:
        d.name = table[d.name]
    return table


def resolve_imports(program: Program, source: str, filename: str) -> Program:
    imports = [s for s in program.statements if isinstance(s, ImportDecl)]
    if not imports:
        return program

    modules: Dict[str, Dict[str, str]] = {}     # alias -> {nom: nom_préfixé}
    prefix: List[Node] = []
    done: Dict[str, Dict[str, str]] = {}
    for imp in imports:
        mod = imp.path
        if mod not in SUPPORTED:
            raise AirNameError(
                f"module `{mod}` introuvable", imp.line, imp.column, filename=filename, source=source,
                length=len(mod) + 7,
                hint=("modules disponibles : " + ", ".join(SUPPORTED)
                      + " (les imports de fichiers arrivent en v0.5)"))
        if mod not in done:
            prog = _load(mod)
            done[mod] = _mangle_module(prog, mod)
            prefix.extend(st for st in prog.statements if not isinstance(st, ImportDecl))
        modules[imp.alias or mod] = done[mod]

    def rewrite(n):
        if isinstance(n, MethodCall) and isinstance(n.obj, Identifier) and n.obj.name in modules:
            table = modules[n.obj.name]
            if n.method not in table:
                raise AirNameError(
                    f"le module `{n.obj.name}` n'a pas de fonction `{n.method}`", n.line, n.column,
                    filename=filename, source=source, length=len(n.obj.name) + len(n.method) + 1,
                    hint="fonctions disponibles : " + ", ".join(sorted(table)))
            callee = Identifier(name=table[n.method], line=n.line, column=n.column)
            return Call(callee=callee, args=n.args, kwargs=n.kwargs, line=n.line, column=n.column)
        if isinstance(n, MemberAccess) and isinstance(n.obj, Identifier) and n.obj.name in modules:
            table = modules[n.obj.name]
            if n.member not in table:
                raise AirNameError(
                    f"le module `{n.obj.name}` n'a pas de `{n.member}`", n.line, n.column,
                    filename=filename, source=source, length=len(n.obj.name) + len(n.member) + 1,
                    hint="disponible : " + ", ".join(sorted(table)))
            return Identifier(name=table[n.member], line=n.line, column=n.column)
        return n

    body = [s for s in program.statements if not isinstance(s, ImportDecl)]
    _walk_replace(body, rewrite)
    program.statements = prefix + body
    return program
