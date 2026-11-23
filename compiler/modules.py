"""Résolution des modules : bibliothèque standard (`import math`) et fichiers (`import "./utils"`).

Le principe est volontairement simple : le module est parsé et vérifié seul, ses noms sont
préfixés (`math.floor` -> `math__floor`), ses déclarations sont ajoutées au programme avant celles
de l'importateur, et les accès `math.floor(...)` sont réécrits en appels directs.

v0.5 : fonctions et constantes ; `export` contrôle ce qui est visible d'un fichier utilisateur ;
imports imbriqués, partagés (un fichier n'est chargé qu'une fois) et détection des cycles.
v0.6 : les blueprints et traits peuvent aussi être exportés (`geo.Point`, `geo.Point.new(...)`).
"""

from __future__ import annotations

import dataclasses
import os
import re
from typing import Dict, List, Optional, Set

from .ast_nodes import (BlueprintDecl, Call, ExportDecl, ForStmt, FunDecl, Identifier, ImportDecl, Lambda,
                        MemberAccess, MethodCall, NewInstance, Node, Param, Program, ResultPattern,
                        TraitDecl, TryCatch, TypeAnnotation, VarDecl)
from .errors import AirError, AirNameError
from .lexer import Lexer
from .parser import Parser

STDLIB_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "stdlib"))
SUPPORTED = ("io", "math", "string", "list")   # modules de la bibliothèque standard


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


def _binders(root) -> Set[str]:
    """Noms liés localement (paramètres, variables, boucles, catch, motifs) : jamais renommés."""
    names: Set[str] = set()

    def collect(n):
        if isinstance(n, (VarDecl, Param)):
            names.add(n.name)
        elif isinstance(n, ForStmt):
            names.add(n.var)
            if n.index_var:
                names.add(n.index_var)
        elif isinstance(n, TryCatch):
            names.add(n.error_var)
        elif isinstance(n, ResultPattern):
            names.add(n.var)
        return n
    _walk_replace(root, collect)
    return names


def _local_names(fun: FunDecl) -> Set[str]:
    return _binders(fun.params) | _binders(fun.body)


_ACTIVE: List[str] = []     # fichiers en cours de vérification (pour voir les cycles à travers `check`)


class _Module:
    def __init__(self, table: Dict[str, str], exported: Set[str], visible_all: bool):
        self.table = table                      # nom -> nom préfixé (fonctions, constantes ET types)
        self.exported = exported                # noms visibles depuis l'extérieur
        self.visible_all = visible_all
        self.types: Set[str] = set()            # parmi `table`, les blueprints et traits


class _Loader:
    """État partagé d'une compilation : modules déjà chargés, déclarations à ajouter, pile des imports."""

    def __init__(self):
        self.cache: Dict[str, _Module] = {}
        self.decls: List[Node] = []
        self.stack: List[str] = []
        self.count = 0

    def stdlib(self, name: str) -> _Module:
        key = "std:" + name
        if key not in self.cache:
            path = os.path.join(STDLIB_DIR, name + ".air")
            self.cache[key] = self._load(path, name, f"{name}__", visible_all=True)
        return self.cache[key]

    def file(self, path: str) -> _Module:
        key = os.path.realpath(path)
        if key in self.cache:
            return self.cache[key]
        if key in self.stack:
            chain = " -> ".join(os.path.basename(p) for p in self.stack[self.stack.index(key):] + [key])
            raise _Cycle(chain)
        self.count += 1
        base = re.sub(r"\W", "_", os.path.splitext(os.path.basename(path))[0])
        self.cache[key] = self._load(path, key, f"{base}_{self.count}__", visible_all=False)
        return self.cache[key]

    def _load(self, path: str, key: str, prefix: str, visible_all: bool) -> _Module:
        with open(path, encoding="utf-8") as f:
            src = f.read()
        if not visible_all:                      # erreurs de types affichées avec le bon fichier
            from .driver import check
            _ACTIVE.append(os.path.realpath(path))
            try:
                check(src, path)
            finally:
                _ACTIVE.pop()
        self.stack.append(os.path.realpath(path))
        try:
            prog = Parser(Lexer(src, path).tokenize(), source=src, filename=path).parse()
            body = resolve_into(prog, src, path, self)
        finally:
            self.stack.pop()
        table: Dict[str, str] = {}
        exported: Set[str] = set()
        types: Set[str] = set()
        decls: List[Node] = []
        for st in body:
            d = st.declaration if isinstance(st, ExportDecl) else st
            if isinstance(d, (FunDecl, VarDecl, BlueprintDecl, TraitDecl)):
                table[d.name] = prefix + d.name
                if isinstance(d, (BlueprintDecl, TraitDecl)):
                    types.add(d.name)
                if isinstance(st, ExportDecl):
                    exported.add(d.name)
                decls.append(st)
            else:
                raise AirNameError(
                    "déclaration non supportée dans un module", st.line, st.column,
                    filename=path, source=src, length=3,
                    hint="un module ne contient que des fonctions, constantes, blueprints, traits et imports")
        value_table = {n: m for n, m in table.items() if n not in types}
        type_table = {n: table[n] for n in types}

        def rename_types(n):
            if isinstance(n, TypeAnnotation) and n.name in type_table:
                n.name = type_table[n.name]
            elif isinstance(n, NewInstance) and n.blueprint in type_table:
                n.blueprint = type_table[n.blueprint]
            elif isinstance(n, BlueprintDecl):
                if n.extends in type_table:
                    n.extends = type_table[n.extends]
                n.implements = [type_table.get(i, i) for i in n.implements]
            return n

        def rename_values(root, shadow):
            def ren(n):
                if isinstance(n, Identifier) and n.name in value_table and n.name not in shadow:
                    n.name = value_table[n.name]
                return n
            return _walk_replace(root, ren)

        for st in decls:
            d = st.declaration if isinstance(st, ExportDecl) else st
            _walk_replace(d, rename_types)
            if isinstance(d, FunDecl):
                rename_values(d.body, _local_names(d))
                for p in d.params:
                    if p.default is not None:
                        p.default = rename_values(p.default, set())
            elif isinstance(d, VarDecl):
                if d.value is not None:
                    d.value = rename_values(d.value, set())
            elif isinstance(d, BlueprintDecl):
                fields = {f.name for f in d.fields}
                for f in d.fields:
                    if getattr(f, "default", None) is not None:
                        f.default = rename_values(f.default, set())
                for m in d.methods:
                    rename_values(m.body, _local_names(m) | fields)
                    for p in m.params:
                        if p.default is not None:
                            p.default = rename_values(p.default, set())
            elif isinstance(d, TraitDecl):
                pass
        for st in decls:
            d = st.declaration if isinstance(st, ExportDecl) else st
            d.name = table[d.name]
        self.decls.extend(decls)
        mod = _Module(table, set(table) if visible_all else exported, visible_all)
        mod.types = types
        return mod


class _Cycle(Exception):
    pass


def _alias_of(imp: ImportDecl) -> str:
    if imp.alias:
        return imp.alias
    return re.sub(r"\W", "_", os.path.splitext(os.path.basename(imp.path))[0])


def resolve_into(program: Program, source: str, filename: str, loader: _Loader) -> List[Node]:
    """Charge les imports de `program` ; retourne ses déclarations sans les `import`, accès réécrits."""
    imports = [s for s in program.statements if isinstance(s, ImportDecl)]
    body = [s for s in program.statements if not isinstance(s, ImportDecl)]
    modules: Dict[str, _Module] = {}
    base_dir = os.path.dirname(os.path.abspath(filename)) if not filename.startswith("<") else os.getcwd()
    for imp in imports:
        span = len(imp.path) + 9
        is_file = "/" in imp.path or imp.path.startswith(".") or imp.path.endswith(".air")
        if not is_file and imp.path in SUPPORTED:
            mod = loader.stdlib(imp.path)
        elif not is_file:
            raise AirNameError(
                f"module `{imp.path}` introuvable", imp.line, imp.column, filename=filename, source=source,
                length=span,
                hint=("modules standard : " + ", ".join(SUPPORTED)
                      + ' ; pour un fichier, écrivez le chemin : import "./' + imp.path + '"'))
        else:
            path = os.path.normpath(os.path.join(base_dir, imp.path))
            if not path.endswith(".air"):
                path += ".air"
            if not os.path.isfile(path):
                raise AirNameError(
                    f"fichier introuvable : {imp.path}", imp.line, imp.column, filename=filename,
                    source=source, length=span, hint=f"cherché ici : {path}")
            try:
                mod = loader.file(path)
            except _Cycle as c:
                raise AirNameError(
                    f"import circulaire : {c}", imp.line, imp.column, filename=filename, source=source,
                    length=span, hint="extrayez le code commun dans un troisième fichier")
        modules[_alias_of(imp)] = mod

    def lookup(n, member: str, length: int):
        mod = modules[n.obj.name]
        if member not in mod.table:
            raise AirNameError(
                f"le module `{n.obj.name}` n'a pas de `{member}`", n.line, n.column, filename=filename,
                source=source, length=length,
                hint="disponible : " + (", ".join(sorted(mod.exported)) or "(rien d'exporté)"))
        if member not in mod.exported:
            raise AirNameError(
                f"`{member}` n'est pas exporté par `{n.obj.name}`", n.line, n.column, filename=filename,
                source=source, length=length, hint=f"ajoutez `export` devant `{member}` dans le module")
        return Identifier(name=mod.table[member], line=n.line, column=n.column)

    def type_lookup(n, dotted: str):
        alias, member = dotted.split(".", 1)
        if alias not in modules:
            return dotted                               # laissé tel quel : le vérificateur signalera l'erreur
        mod = modules[alias]
        if member not in mod.types:
            raise AirNameError(
                f"le module `{alias}` n'a pas de type `{member}`", n.line, n.column, filename=filename,
                source=source, length=len(dotted),
                hint="types disponibles : " + (", ".join(sorted(mod.types & mod.exported)) or "(aucun)"))
        if member not in mod.exported:
            raise AirNameError(
                f"`{member}` n'est pas exporté par `{alias}`", n.line, n.column, filename=filename,
                source=source, length=len(dotted), hint=f"ajoutez `export` devant `{member}` dans le module")
        return mod.table[member]

    def rewrite(n):
        if isinstance(n, TypeAnnotation) and "." in n.name:
            n.name = type_lookup(n, n.name)
        elif isinstance(n, NewInstance) and "." in n.blueprint:
            n.blueprint = type_lookup(n, n.blueprint)
        elif isinstance(n, BlueprintDecl):
            if n.extends and "." in n.extends:
                n.extends = type_lookup(n, n.extends)
            n.implements = [type_lookup(n, i) if "." in i else i for i in n.implements]
        if isinstance(n, MethodCall) and isinstance(n.obj, Identifier) and n.obj.name in modules:
            callee = lookup(n, n.method, len(n.obj.name) + len(n.method) + 1)
            return Call(callee=callee, args=n.args, kwargs=n.kwargs, line=n.line, column=n.column)
        if isinstance(n, MemberAccess) and isinstance(n.obj, Identifier) and n.obj.name in modules:
            return lookup(n, n.member, len(n.obj.name) + len(n.member) + 1)
        return n

    if modules:
        _walk_replace(body, rewrite)
    return body


def resolve_imports(program: Program, source: str, filename: str) -> Program:
    loader = _Loader()
    loader.stack.extend(_ACTIVE)
    if filename and not filename.startswith("<") and os.path.realpath(filename) not in loader.stack:
        loader.stack.append(os.path.realpath(filename))
    body = resolve_into(program, source, filename, loader)
    program.statements = loader.decls + body
    return program
